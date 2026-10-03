"""阿里云百炼 DashScope 服务：语音识别（ASR）+ 语音合成（TTS）+ 定制热词。

- ASR：paraformer-realtime-v2，本地 WAV 文件流式送入 WebSocket（不需要公网 URL）。
- TTS：cosyvoice-v2，整段合成 WAV（16k 单声道，后续可直接给基座喇叭播放）。
- 热词：VocabularyService 创建热词表，识别时挂 vocabulary_id 提升专有名词准确率。

任何失败都抛出带清晰信息的异常，由调用方决定降级策略。
"""
import logging
import threading
import uuid
from pathlib import Path

from ..config import settings, APP_ROOT

logger = logging.getLogger(__name__)

_uploaded_dir = APP_ROOT / "uploads"
_audio_dir = _uploaded_dir / "audio"
_card_dir = _uploaded_dir / "cards"

# 热词表缓存：短语集合不变时复用同一个 vocabulary_id（避免重复创建计费项）
_vocab_lock = threading.Lock()
_vocab_cache: dict[str, str] = {}  # key: phrases fingerprint -> vocabulary_id


def ensure_dirs() -> None:
    _audio_dir.mkdir(parents=True, exist_ok=True)
    _card_dir.mkdir(parents=True, exist_ok=True)


def _require_api_key() -> str:
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置")
    return settings.dashscope_api_key


def _fix_wav_bytes(data: bytes) -> bytes:
    """修正流式 TTS 返回的 WAV 头部：size 字段可能是占位垃圾值，按实际长度重写。"""
    import struct

    if len(data) < 44 or data[0:4] != b"RIFF":
        return data
    declared_riff = int.from_bytes(data[4:8], "little")
    declared_data = int.from_bytes(data[40:44], "little")
    if declared_riff + 8 > len(data) or declared_data + 36 > len(data):
        data = (
            data[:4] + struct.pack("<I", len(data) - 8) + data[8:40]
            + struct.pack("<I", len(data) - 44) + data[44:]
        )
    return data


def synthesize_tts(text: str) -> Path:
    """整段合成 WAV，返回文件路径。"""
    api_key = _require_api_key()
    ensure_dirs()
    import dashscope
    from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer

    dashscope.api_key = api_key
    synth = SpeechSynthesizer(
        model=settings.dashscope_tts_model,
        voice=settings.dashscope_tts_voice,
        format=AudioFormat.WAV_16000HZ_MONO_16BIT,
    )
    audio = synth.call(text)
    if not audio:
        raise RuntimeError(f"TTS 合成返回空音频（model={settings.dashscope_tts_model}）")
    out = _audio_dir / f"tts_{uuid.uuid4().hex[:12]}.wav"
    out.write_bytes(_fix_wav_bytes(audio))
    return out


def create_vocabulary(phrases: list[dict]) -> str:
    """创建/复用 ASR 热词表，返回 vocabulary_id。phrases: [{phrase, weight}]。"""
    api_key = _require_api_key()
    import dashscope
    from dashscope.audio.asr import VocabularyService

    fingerprint = "|".join(f"{p['phrase']}:{p.get('weight', 3)}" for p in sorted(
        phrases, key=lambda x: x["phrase"]))
    with _vocab_lock:
        if fingerprint in _vocab_cache:
            return _vocab_cache[fingerprint]
        dashscope.api_key = api_key
        svc = VocabularyService()
        resp = svc.create_vocabulary(
            prefix="fridgepal", phrases=[
                {"phrase": p["phrase"], "weight": int(p.get("weight", 3))}
                for p in phrases
            ],
        )
        if resp.status_code != 200:
            raise RuntimeError(f"热词表创建失败: {resp.code} {resp.message}")
        vocab_id = resp.output["vocabulary_id"]
        _vocab_cache[fingerprint] = vocab_id
        return vocab_id


def _wav_to_pcm(path: Path) -> tuple[bytes, int, int]:
    """解析 WAV，返回 (data块裸PCM, 采样率, 声道数)。

    不信任头部 size 字段（TTS 流式输出可能是占位值）：Python 切片自动截到文件尾，
    因此 data 块取到文件结束即为真实音频。
    """
    import struct

    data = path.read_bytes()
    if len(data) < 44 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise RuntimeError("不是有效的 WAV 文件")
    fmt = None
    pos = 12
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = int.from_bytes(data[pos + 4:pos + 8], "little")
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = body
        elif cid == b"data":
            if fmt is None:
                raise RuntimeError("WAV 缺少 fmt 块")
            channels = struct.unpack("<H", fmt[2:4])[0]
            rate = struct.unpack("<I", fmt[4:8])[0]
            bits = struct.unpack("<H", fmt[14:16])[0]
            if bits != 16:
                raise RuntimeError(f"暂只支持 16bit WAV（当前 {bits}bit）")
            if channels == 2:
                import audioop

                body = audioop.tomono(body, 2, 0.5, 0.5)
                channels = 1
            return body, rate, channels
        pos += 8 + size + (size & 1)
    raise RuntimeError("WAV 缺少 data 块")


def transcribe_wav(path: str | Path, phrases: list[dict] | None = None) -> str:
    """识别本地 WAV，返回合并后的文本。phrases: 热词列表 [{phrase, weight}]。"""
    api_key = _require_api_key()
    import dashscope
    from dashscope.audio.asr import Recognition, RecognitionCallback

    dashscope.api_key = api_key
    path = Path(path)

    vocab_id: str | None = None
    try:
        if phrases:
            vocab_id = create_vocabulary(phrases)
    except Exception as e:  # 热词失败不阻塞识别
        logger.warning("热词表不可用，跳过: %s", e)

    collected: list[str] = []
    errors: list[str] = []
    pcm, sample_rate, channels = _wav_to_pcm(Path(path))
    logger.info("ASR 输入: %d bytes PCM, %dHz, %dch", len(pcm), sample_rate, channels)

    class _CB(RecognitionCallback):
        def on_open(self) -> None:
            logger.debug("ASR 连接已建立")

        def on_event(self, result) -> None:
            sentence = result.get_sentence()
            if not sentence:
                return
            text = sentence.get("text", "")
            if text and sentence.get("sentence_end"):
                collected.append(text)

        def on_complete(self) -> None:
            logger.debug("ASR 完成")

        def on_error(self, error) -> None:
            errors.append(str(getattr(error, "message", error)))

        def on_close(self) -> None:
            pass

    rec = Recognition(
        model=settings.dashscope_asr_model,
        format="pcm",
        sample_rate=sample_rate,
        callback=_CB(),
        vocabulary_id=vocab_id,
    )
    rec.start()
    try:
        for i in range(0, len(pcm), 6400):
            rec.send_audio_frame(pcm[i:i + 6400])
    finally:
        rec.stop()

    if errors:
        raise RuntimeError(f"ASR 识别失败: {'; '.join(errors)}")
    text = "".join(collected).strip()
    if not text:
        raise RuntimeError("ASR 未返回文本")
    return text
