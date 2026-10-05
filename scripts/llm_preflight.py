"""D5-R1 LLM 连通预检与推理档位探测。

- 默认：加载生产配置（含 ``LLM_EXTRA_BODY``）发起最小请求，**断言 ``content`` 非空**，
  打印 model / base_url / 延迟 / 用量 / reasoning_tokens；失败退出码 1。
- ``--probe-reasoning``：对同一最小请求跑三组（基线 / ``thinking=enabled`` +
  ``reasoning_effort=low`` / ``thinking=disabled``），打印每组 ``content`` 与
  ``reasoning_tokens``，用于确定生产推荐配置（输出贴回后写入 .env.example / README）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

from openai import OpenAI  # noqa: E402

PROMPT = 'Reply with exactly this JSON and nothing else: {"ok": true}'
DEFAULT_MAX_TOKENS = 512


def _extra_body() -> dict:
    raw = (os.environ.get("LLM_EXTRA_BODY") or "").strip()
    return json.loads(raw) if raw else {}


def _reasoning_tokens(usage):
    if usage is None:
        return None
    details = getattr(usage, "completion_tokens_details", None)
    if details is not None and getattr(details, "reasoning_tokens", None) is not None:
        return details.reasoning_tokens
    return getattr(usage, "reasoning_tokens", None)


def _invoke(client, model, extra_body):
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": DEFAULT_MAX_TOKENS,
        "temperature": 0,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body
    started = time.time()
    response = client.chat.completions.create(**kwargs)
    latency = time.time() - started
    content = response.choices[0].message.content if response.choices else None
    return content, getattr(response, "usage", None), latency


def _probe(client, model):
    base = _extra_body()
    cases = [
        ("baseline", {}),
        (
            "thinking_enabled_low",
            {"thinking": {"type": "enabled"}, "reasoning_effort": "low"},
        ),
        ("thinking_disabled", {"thinking": {"type": "disabled"}}),
    ]
    print(f"model={model}（探测三组，max_tokens={DEFAULT_MAX_TOKENS}）")
    for name, overlay in cases:
        merged = {**base, **overlay}
        try:
            content, usage, latency = _invoke(client, model, merged)
            print(
                f"  [{name}] latency={latency:.2f}s "
                f"reasoning_tokens={_reasoning_tokens(usage)} content={content!r}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  [{name}] ERROR {type(exc).__name__}: {exc}")
    print(
        "提示：成功标准 = 找到一组 reasoning_tokens 趋零且 content 非空；"
        "把该组写入 .env 的 LLM_EXTRA_BODY，并附官方文档确认的 thinking.type / reasoning_effort 合法值。"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 连通预检 / 推理档位探测")
    parser.add_argument("--probe-reasoning", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    base_url = os.environ.get("OPENAI_BASE_URL") or None
    if not api_key:
        print("[FAIL] OPENAI_API_KEY 未配置（.env 内为空）")
        return 1
    if not model:
        print("[FAIL] OPENAI_MODEL 未配置")
        return 1

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=float(os.environ.get("LLM_TIMEOUT", "30")),
    )
    if args.probe_reasoning:
        return _probe(client, model)

    try:
        content, usage, latency = _invoke(client, model, _extra_body())
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 调用失败：{type(exc).__name__}: {exc}")
        return 1

    print(f"model={model}")
    print(f"base_url={base_url}")
    print(f"latency={latency:.2f}s")
    print(f"usage={usage}")
    print(f"reasoning_tokens={_reasoning_tokens(usage)}")
    print(f"content={content!r}")
    if not content:
        print("[FAIL] content 为空（可能被 max_tokens 耗尽/截断）")
        return 1
    print("[OK] preflight passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())