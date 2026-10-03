"""设备模拟器：在电脑上模拟「对着冰箱贴说话」。

用法（先启动后端）：
    python device_simulator.py
    python device_simulator.py --sn SN-MY-001

进入后直接输入中文，例如：
    放了两盒牛奶、一袋鸡蛋大概30个
    冰箱里有什么
    牛奶喝完了
    要买酱油和纸巾
    退出 / quit

后续会扩展为：模拟麦端录音 → 上传 → ASR → 对话的完整链路（M1 后半段）。
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

BASE_URL = "http://127.0.0.1:8000"


def register_device(sn: str) -> tuple[str, str]:
    r = httpx.post(
        f"{BASE_URL}/api/v1/device/register",
        json={"device_sn": sn, "device_type": "base"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    return data["device_id"], data["device_token"]


def chat(user_id: str, text: str) -> dict:
    r = httpx.post(
        f"{BASE_URL}/api/v1/ai/chat",
        json={"user_id": user_id, "channel": "voice", "text": text},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="FridgePal 设备模拟器")
    parser.add_argument("--sn", default=f"SN-DEV-{uuid.uuid4().hex[:6].upper()}")
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.base_url

    print("=" * 50)
    print("FridgePal 设备模拟器")
    print(f"设备SN: {args.sn}")
    print("（先确保后端已启动：uvicorn app.main:app --reload）")
    print("=" * 50)

    try:
        device_id, _token = register_device(args.sn)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 连接后端失败：{exc}")
        print("请先启动后端再试。")
        sys.exit(1)

    user_id = input("你的用户ID（直接回车用默认）: ").strip() or "dev-user-001"

    print("\n好了，开始说吧（输入 退出 结束）：\n")
    while True:
        try:
            text = input("你说> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见 👋")
            break
        if not text:
            continue
        if text in ("退出", "quit", "exit"):
            print("再见 👋")
            break
        try:
            resp = chat(user_id, text)
            print(f"  回复> {resp['reply_text']}")
            if resp.get("display_text"):
                print(f"  屏显> {resp['display_text']}")
            for action in resp.get("actions") or []:
                print(f"  执行> {json.dumps(action, ensure_ascii=False)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ❌ 出错：{exc}")


if __name__ == "__main__":
    main()
