"""D5-R1：LLM 客户端层验收测试（T1 live / T2 transport / T3 craft）。

- T1 ``@pytest.mark.live``：真打——连通 + 结构化输出、截断 → 错误分类 → AgentRun failed。
- T2 ``@pytest.mark.transport``：HTTP 边界 mock（构造异常 API 返回体），测我方解析/校验。
- T3 craft（无标记）：canonical input_hash 稳定性、错误分类映射、fake 后端回放、键缺失 fail-loud。

沙箱无 LLM 出网：沙箱内 `pytest -q -m "not live"`；T1 交用户本机取证。
"""

import pytest
from django.core.management import call_command
from pydantic import BaseModel

from agents import llm
from agents.models import AgentRun
from core.models import Project, User


class Resp(BaseModel):
    ok: bool | None = None


class Strict(BaseModel):
    ok: bool


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


# --- fake response helpers（T2）--------------------------------------------
class _Msg:
    def __init__(self, content, refusal=None):
        self.content = content
        self.refusal = refusal


class _Choice:
    def __init__(self, content, finish_reason="stop", refusal=None):
        self.message = _Msg(content, refusal)
        self.finish_reason = finish_reason


class _Usage:
    prompt_tokens = 1
    completion_tokens = 1
    total_tokens = 2


class _Response:
    def __init__(self, content, finish_reason="stop", refusal=None):
        self.choices = [_Choice(content, finish_reason, refusal)]
        self.usage = _Usage()


# --- T3 craft --------------------------------------------------------------
def test_canonical_input_hash_stable():
    a = {"b": 1, "a": [1, 2]}
    b = {"a": [1, 2], "b": 1}  # 键序不同
    assert llm.canonical_input_hash(a) == llm.canonical_input_hash(b)
    assert llm.canonical_input_hash(a) != llm.canonical_input_hash({"a": [1, 2], "b": 2})
    assert len(llm.canonical_input_hash(a)) == 64


def test_error_classification_map():
    import httpx
    import openai

    request = httpx.Request("POST", "https://example.invalid")
    rate = openai.RateLimitError("rate", response=httpx.Response(429, request=request), body=None)
    connection = openai.APIConnectionError(request=request)
    server = openai.APIStatusError("boom", response=httpx.Response(500, request=request), body=None)

    assert isinstance(llm._classify(rate, "json_schema"), llm.RateLimitError)
    assert isinstance(llm._classify(connection, "json_schema"), llm.TransportError)
    assert isinstance(llm._classify(server, "json_schema"), llm.TransportError)
    assert llm._is_retryable(rate) is True
    assert llm._is_retryable(server) is True
    assert llm._is_retryable(connection) is False


def test_fake_backend_replay(monkeypatch, settings, seeded, project):
    monkeypatch.setattr(settings, "LLM_BACKEND", "fake")
    before = AgentRun.objects.count()
    result = llm.call_json(
        Resp,
        [{"role": "user", "content": "x"}],
        "smoke",
        "v1",
        project=project,
        agent_name="requirement",
    )
    assert result.parsed.ok is True
    assert result.structured_mode == "fake"
    assert AgentRun.objects.count() == before  # fake 不发起真实调用、不落 AgentRun


def test_missing_key_fails_loud(monkeypatch, settings, seeded, project):
    monkeypatch.setattr(settings, "LLM_BACKEND", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    before = AgentRun.objects.count()
    with pytest.raises(llm.LLMConfigError) as excinfo:
        llm.call_json(
            Resp,
            [{"role": "user", "content": "x"}],
            "k",
            "v1",
            project=project,
            agent_name="requirement",
        )
    assert "OPENAI_API_KEY" in str(excinfo.value)
    assert AgentRun.objects.count() == before  # 本地预检失败不产生 AgentRun


# --- T2 transport ----------------------------------------------------------
@pytest.mark.transport
def test_transport_schema_invalid(monkeypatch, settings, seeded, project):
    monkeypatch.setattr(settings, "LLM_BACKEND", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "test-model")
    monkeypatch.setattr(llm, "_request", lambda *a, **k: _Response('{"unexpected": 1}'))
    with pytest.raises(llm.SchemaInvalidError):
        llm.call_json(
            Strict,
            [{"role": "user", "content": "x"}],
            "t-schema",
            "v1",
            project=project,
            agent_name="requirement",
        )


@pytest.mark.transport
def test_transport_client_parse(monkeypatch, settings, seeded, project):
    monkeypatch.setattr(settings, "LLM_BACKEND", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "OPENAI_MODEL", "test-model")
    monkeypatch.setattr(llm, "_request", lambda *a, **k: _Response("not a json at all"))
    with pytest.raises(llm.ClientParseError):
        llm.call_json(
            Resp,
            [{"role": "user", "content": "x"}],
            "t-parse",
            "v1",
            project=project,
            agent_name="requirement",
        )


# --- T1 live（本机取证；沙箱 -m "not live" 跳过）---------------------------
@pytest.mark.live
def test_live_connectivity_and_schema(seeded, project):
    before = AgentRun.objects.count()
    result = llm.call_json(
        Resp,
        [{"role": "user", "content": 'Return exactly {"ok": true} as JSON.'}],
        "smoke",
        "v1",
        max_tokens=512,
        project=project,
        agent_name="requirement",
    )
    assert result.parsed.ok is True
    assert result.usage is not None
    assert result.structured_mode in ("json_schema", "json_object")
    assert AgentRun.objects.count() == before + 1
    run = AgentRun.objects.order_by("-id").first()
    assert run.status == "needs_review"
    assert run.output_schema_valid is True
    assert run.reference_check_passed is None
    assert len(run.input_hash) == 64


@pytest.mark.live
def test_live_truncation(seeded, project):
    class Essay(BaseModel):
        text: str

    before = AgentRun.objects.count()
    with pytest.raises((llm.TruncationError, llm.ClientParseError)):
        llm.call_json(
            Essay,
            [{"role": "user", "content": "Write a detailed 500-word essay about gateways."}],
            "trunc",
            "v1",
            max_tokens=8,
            project=project,
            agent_name="requirement",
        )
    assert AgentRun.objects.count() == before + 1
    run = AgentRun.objects.order_by("-id").first()
    assert run.status == "failed"
    assert run.output_json["error_type"] in ("truncation", "client_parse")
    assert "structured_mode" in run.output_json    # D12-R2（JSON-002 T1 补强）：truncation 非 schema 失败 → output_schema_valid=None（ADR-0008）
    assert run.output_schema_valid is None
    assert run.confirmed_by_id is None and run.confirmed_at is None  # 四值绑定