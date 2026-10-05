"""D5-R1 Step 0：LLM 连通预检（fail-fast）。

单次最小调用，打印 model / base_url / 用量 / 延迟；失败打印原因并退出码 1。
配置来源：`.env`（`OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL`）。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

from openai import OpenAI  # noqa: E402


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    base_url = os.environ.get("OPENAI_BASE_URL") or None

    if not api_key:
        print("[FAIL] OPENAI_API_KEY 未配置（.env 内为空）")
        return 1
    if not model:
        print("[FAIL] OPENAI_MODEL 未配置")
        return 1

    client = OpenAI(api_key=api_key, base_url=base_url)
    started = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": 'Reply with exactly this JSON and nothing else: {"ok": true}',
                }
            ],
            max_tokens=32,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 调用失败：{type(exc).__name__}: {exc}")
        return 1

    latency = time.time() - started
    content = response.choices[0].message.content if response.choices else None
    usage = getattr(response, "usage", None)
    print(f"model={model}")
    print(f"base_url={base_url}")
    print(f"latency={latency:.2f}s")
    print(f"usage={usage}")
    print(f"content={content!r}")
    print("[OK] preflight passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())