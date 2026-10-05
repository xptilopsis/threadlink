"""LLM 客户端层（D5-R1）。

职责：

- ``call_json``：以 OpenAI SDK 发起**结构化输出**调用，返回 Pydantic 实例；
- **provider 自适应结构化模式**：``auto`` 先按 ``json_schema``(strict) 发起，
  若端点报「不支持该参数」类错误 → 自动降级 ``json_object`` 重发一次（记录实际模式）；
  ``LLM_STRUCTURED_MODE`` 显式配置 ``json_schema`` / ``json_object`` 时直接使用；
- 错误分类：``TransportError`` / ``RateLimitError`` / ``TruncationError`` /
  ``RefusalError`` / ``SchemaInvalidError`` / ``ClientParseError`` / ``LLMConfigError``；
- retry **仅对 5xx / 限流**，≤ ``LLM_MAX_RETRIES`` 次、指数退避；其余不重试；
- 每次**实际发起**调用（成功/失败）落 ``AgentRun``（R1 边界：本地预检失败不落）；
- ``LLM_BACKEND=fake`` 从 ``tests/fixtures/llm_fake/<prompt_id>.json`` 读预置响应，
  供断网开发（**不发起真实调用、不落 AgentRun**；pytest 默认不使用）。

字段名以 ``agents.models.AgentRun`` 与 ``docs/interface_contract.md`` §6 为准。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings

from agents.models import AgentRun

FAKE_FIXTURE_DIR = Path(settings.BASE_DIR) / "tests" / "fixtures" / "llm_fake"
DEFAULT_MAX_TOKENS = 1024
RAW_SNIPPET_LIMIT = 500


# ---------------------------------------------------------------------------
# 错误分类
# ---------------------------------------------------------------------------


class LLMError(Exception):
    category = "llm_error"

    def __init__(self, message: str, *, raw: str | None = None, structured_mode: str | None = None):
        super().__init__(message)
        self.raw = raw
        self.structured_mode = structured_mode


class TransportError(LLMError):
    category = "transport"


class RateLimitError(LLMError):
    category = "rate_limit"


class TruncationError(LLMError):
    category = "truncation"


class RefusalError(LLMError):
    category = "refusal"


class SchemaInvalidError(LLMError):
    category = "schema_invalid"


class ClientParseError(LLMError):
    category = "client_parse"


class LLMConfigError(LLMError):
    """本地配置/预检失败（未发起真实调用；不落 AgentRun）。"""

    category = "config"


@dataclass
class CallResult:
    parsed: Any
    raw_output: str
    usage: Any
    latency: float
    structured_mode: str
    agent_run: Any = None  # D5-R2：真实调用落库的 AgentRun 行（供核验后同一行更新）


# ---------------------------------------------------------------------------
# canonical input hash
# ---------------------------------------------------------------------------


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def canonical_input_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 落库（仅真实调用路径）
# ---------------------------------------------------------------------------


def _record_agent_run(
    *,
    project,
    agent_name,
    prompt_id,
    prompt_version,
    model,
    temperature,
    input_payload,
    status,
    output_json,
    output_schema_valid,
    error="",
):
    return AgentRun.objects.create(
        project=project,
        agent_name=agent_name,
        status=status,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        model=str(model)[:64],
        temperature=temperature,
        input_json=input_payload,
        input_hash=canonical_input_hash(input_payload),
        output_json=output_json,
        output_schema_valid=output_schema_valid,
        reference_check_passed=None,
        invalid_references=[],
        error=error,
    )


# ---------------------------------------------------------------------------
# 真实调用
# ---------------------------------------------------------------------------


def _is_unsupported_response_format(exc: Exception) -> bool:
    text = str(exc).lower()
    if "response_format" not in text and "json_schema" not in text:
        return False
    return any(
        token in text
        for token in ("not support", "unsupported", "invalid", "unavailable", "recognized")
    )


def _is_retryable(exc: Exception) -> bool:
    import openai

    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIStatusError):
        return getattr(exc, "status_code", 0) >= 500
    return False


def _classify(exc: Exception, structured_mode: str, raw: str | None = None) -> LLMError:
    import openai

    if isinstance(exc, openai.RateLimitError):
        return RateLimitError(f"限流：{exc}", raw=raw, structured_mode=structured_mode)
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return TransportError(f"连接失败：{exc}", raw=raw, structured_mode=structured_mode)
    if isinstance(exc, openai.APIStatusError):
        return TransportError(
            f"HTTP {exc.status_code}：{exc}", raw=raw, structured_mode=structured_mode
        )
    return TransportError(f"{type(exc).__name__}: {exc}", raw=raw, structured_mode=structured_mode)


def _extra_body() -> dict | None:
    """解析 ``settings.LLM_EXTRA_BODY``（JSON 字符串）→ dict；空则 None。

    通用 provider 参数注入（不写死任何 provider 特判）；非法 JSON → ``LLMConfigError``
    （本地配置错误，不落 AgentRun）。fake 后端不读取本项。
    """

    raw = (getattr(settings, "LLM_EXTRA_BODY", "") or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMConfigError(f"LLM_EXTRA_BODY 不是合法 JSON：{exc}")
    if not isinstance(data, dict):
        raise LLMConfigError("LLM_EXTRA_BODY 必须是 JSON 对象")
    return data or None


def _request(client, schema_model, messages, model, temperature, max_tokens, mode, extra_body=None):
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if extra_body:
        kwargs["extra_body"] = extra_body
    if mode == "json_schema":
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_model.__name__,
                "schema": schema_model.model_json_schema(),
                "strict": True,
            },
        }
    elif mode == "json_object":
        kwargs["response_format"] = {"type": "json_object"}
    return client.chat.completions.create(**kwargs)


def _messages_for_json_object(schema_model, messages):
    hint = (
        "Respond with a single JSON object (valid json) matching this schema: "
        f"{json.dumps(schema_model.model_json_schema(), ensure_ascii=False)}"
    )
    return [{"role": "system", "content": hint}, *messages]


def _parse_response(schema_model, response, structured_mode):
    from pydantic import ValidationError

    choice = response.choices[0]
    message = choice.message
    content = message.content
    finish_reason = getattr(choice, "finish_reason", None)
    refusal = getattr(message, "refusal", None)

    if finish_reason == "length":
        raise TruncationError(
            "输出被 max_tokens 截断（finish_reason=length）",
            raw=content,
            structured_mode=structured_mode,
        )
    if refusal:
        raise RefusalError(f"模型拒绝：{refusal}", raw=content, structured_mode=structured_mode)
    if not content:
        raise ClientParseError("空响应，无法解析为 JSON", raw=content, structured_mode=structured_mode)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ClientParseError(
            f"响应非合法 JSON：{exc}", raw=content, structured_mode=structured_mode
        ) from exc
    try:
        parsed = schema_model.model_validate(data)
    except ValidationError as exc:
        raise SchemaInvalidError(
            f"Pydantic 校验失败：{exc}", raw=content, structured_mode=structured_mode
        ) from exc
    return parsed, content


def _call_openai(schema_model, messages, model, temperature, max_tokens, requested_mode):
    import openai

    client = openai.OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.LLM_TIMEOUT,
    )
    mode = "json_schema" if requested_mode == "auto" else requested_mode
    extra_body = _extra_body()
    response = None
    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        try:
            response = _request(
                client, schema_model, messages, model, temperature, max_tokens, mode, extra_body
            )
            break
        except Exception as exc:  # noqa: BLE001
            if (
                requested_mode == "auto"
                and mode == "json_schema"
                and _is_unsupported_response_format(exc)
            ):
                mode = "json_object"
                try:
                    response = _request(
                        client,
                        schema_model,
                        _messages_for_json_object(schema_model, messages),
                        model,
                        temperature,
                        max_tokens,
                        mode,
                        extra_body,
                    )
                    break
                except Exception as exc2:  # noqa: BLE001
                    exc = exc2
            if _is_retryable(exc) and attempt < settings.LLM_MAX_RETRIES:
                time.sleep(min(2**attempt, 4))
                continue
            raise _classify(exc, mode)
    parsed, content = _parse_response(schema_model, response, mode)
    return parsed, content, getattr(response, "usage", None), mode


def _call_fake(schema_model, prompt_id):
    path = FAKE_FIXTURE_DIR / f"{prompt_id}.json"
    if not path.exists():
        raise LLMConfigError(f"fake 后端缺少预置响应：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    parsed = schema_model.model_validate(data)
    return parsed, json.dumps(data, ensure_ascii=False), None, "fake"


def _validate_config(model):
    if not settings.OPENAI_API_KEY:
        raise LLMConfigError("OPENAI_API_KEY 未配置（.env 为空）")
    if not model:
        raise LLMConfigError("OPENAI_MODEL 未配置")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def call_json(
    schema_model,
    messages,
    prompt_id,
    prompt_version,
    temperature=0,
    max_tokens=None,
    *,
    project,
    agent_name,
    model=None,
):
    """发起一次结构化输出调用。

    ``project`` / ``agent_name`` 为 ``AgentRun`` 落库所需的必填字段（模型层强制），
    故在指令签名基础上补充为关键字参数。返回 :class:`CallResult`。
    """

    effective_model = model or settings.OPENAI_MODEL
    requested_mode = settings.LLM_STRUCTURED_MODE
    input_payload = {
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "model": effective_model,
        "temperature": temperature,
        "max_tokens": max_tokens if max_tokens is not None else DEFAULT_MAX_TOKENS,
        "messages": messages,
    }
    started = time.time()
    try:
        if settings.LLM_BACKEND == "fake":
            # 断网逃生口：模拟响应，不发起真实调用、不落 AgentRun。
            parsed, raw, usage, used_mode = _call_fake(schema_model, prompt_id)
            return CallResult(parsed, raw, usage, time.time() - started, used_mode)

        _validate_config(effective_model)
        parsed, raw, usage, used_mode = _call_openai(
            schema_model, messages, effective_model, temperature, max_tokens, requested_mode
        )
    except LLMConfigError:
        # 本地预检失败：不产生 AgentRun（R1 边界）
        raise
    except LLMError as exc:
        _record_agent_run(
            project=project,
            agent_name=agent_name,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            model=effective_model,
            temperature=temperature,
            input_payload=input_payload,
            status="failed",
            output_json={
                "error_type": exc.category,
                "error": str(exc),
                "raw": (exc.raw or "")[:RAW_SNIPPET_LIMIT],
                "structured_mode": exc.structured_mode,
            },
            output_schema_valid=(False if exc.category == "schema_invalid" else None),
            error=str(exc),
        )
        raise

    latency = time.time() - started
    run = _record_agent_run(
        project=project,
        agent_name=agent_name,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        model=effective_model,
        temperature=temperature,
        input_payload=input_payload,
        status="needs_review",
        output_json=parsed.model_dump(mode="json"),
        output_schema_valid=True,
    )
    return CallResult(parsed, raw, usage, latency, used_mode, agent_run=run)