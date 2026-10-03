#pragma once
/* 云端客户端：GET TTS 音频、multipart 上传录音。
 * 服务器地址来自配网（如 http://192.168.1.10:8000）。
 */
#include "esp_err.h"
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* GET /api/v1/recordings/tts?text=<urlencode(text)>
 * 成功后 *buf 指向 PSRAM 里的完整 WAV，*len 为长度（调用方用完不需 free，
 * 内部静态复用；两次调用覆盖）。 */
esp_err_t cloud_get_tts(const char *server, const char *text,
                        const uint8_t **buf, size_t *len);

/* POST /api/v1/recordings（multipart：audio=record.wav, user_id=fridgegu,
 * channel=device）。header + pcm 拼成完整 WAV 上传。
 * reply_out 提取 JSON 里的 reply 字段。 */
esp_err_t cloud_upload_recording(const char *server, const uint8_t *wav_header,
                                 size_t header_len, const uint8_t *pcm,
                                 size_t pcm_len, const char *zone,
                                 char *reply_out, size_t reply_len, bool *speak_out);

#ifdef __cplusplus
}
#endif
