"""D5-R2：Requirement Agent 全链测试（T3 craft 沙箱 / T1 live 本机）。

craft：核验器五态、prompt loader fail-loud、队列与入口视图、fake 管道冒烟、
管道核验失败同行更新、seed 文档↔fixture 元数据一致性。
live：demo_email 端到端（卡片数先跑后固化）、只读边界。
"""

import hashlib
import json
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from agents import llm
from agents.models import AgentRun
from agents.prompts import PromptNotFoundError, load
from agents.requirement import PROMPT_ID, PROMPT_VERSION, run_requirement_agent
from agents.verification import verify_references
from config.settings import resolve_doc_path
from core.models import Bom, BomItem, Document, Part, Project, Requirement, User
from core.numbering import numbering_suspended
from schemas.agent_outputs import RequirementAgentOutput
from traceability.models import TraceLink

FIXTURE = Path(settings.BASE_DIR) / "fixtures" / "demo_seed.json"


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


@pytest.fixture
def project(seeded):
    return Project.objects.get(code="DEMO-GW")


# --- §3 核验器五态 ---------------------------------------------------------
def test_verify_pass(seeded, project):
    assert verify_references(project.pk, [{"type": "document", "id": "DOC-001"}]) == []


def test_verify_not_found(seeded, project):
    invalid = verify_references(project.pk, [{"type": "part", "id": "PART-999"}])
    assert len(invalid) == 1
    assert invalid[0].reason == "not_found"


def test_verify_unknown_type(seeded, project):
    invalid = verify_references(project.pk, [{"type": "trace_link", "id": "TL-001"}])
    assert invalid[0].reason == "unknown_type"


def test_verify_wrong_project(seeded, project):
    other = Project.objects.create(code="P2-WP", name="其它项目", created_by=seeded)
    Part.objects.create(project=other, part_number="PART-777", name="别项目物料")
    invalid = verify_references(project.pk, [{"type": "part", "id": "PART-777"}])
    assert invalid[0].reason == "wrong_project"


def test_verify_ambiguous(seeded, project):
    other_bom = Bom.objects.create(
        project=project, name="第二 BOM", version="v9.8", created_by=seeded
    )
    with numbering_suspended():
        BomItem.objects.create(bom=other_bom, item_no="BI-001", part=Part.objects.get(part_number="PART-001"))
    invalid = verify_references(project.pk, [{"type": "bom_item", "id": "BI-001"}])
    assert invalid[0].reason == "ambiguous"


# --- §1 prompt loader fail-loud -------------------------------------------
def test_prompt_loader_missing_fails_loud(monkeypatch):
    from agents import prompts

    monkeypatch.setattr(prompts, "PROMPTS_ROOT", Path("__no_such_dir__"))
    with pytest.raises(PromptNotFoundError) as excinfo:
        prompts.load(PROMPT_ID, PROMPT_VERSION)
    assert "system.md" in str(excinfo.value)


# --- §5 队列与入口视图 -----------------------------------------------------
def test_agentrun_queue_view(seeded, client):
    client.force_login(seeded)
    assert client.get("/admin/agents/agentrun/").status_code == 200
    assert client.get("/admin/agents/agentrun/?status=needs_review").status_code == 200


def test_run_endpoint_anonymous_redirects(seeded, client):
    response = client.post(
        "/agents/requirement/run/", data="{}", content_type="application/json"
    )
    assert response.status_code == 302


# --- fake 管道冒烟（不落库）------------------------------------------------
def test_fake_pipeline_no_agentrun(monkeypatch, settings, seeded, project):
    monkeypatch.setattr(settings, "LLM_BACKEND", "fake")
    document = Document.objects.get(doc_no="DOC-001")
    before = AgentRun.objects.count()
    summary = run_requirement_agent(project, document, seeded)
    assert summary["ok"] is True and summary.get("fake") is True
    assert AgentRun.objects.count() == before  # fake 不落库


# --- 管道核验失败：同一行更新（不新增）-------------------------------------
def test_pipeline_reference_failure_updates_same_row(
    monkeypatch, settings, seeded, project
):
    parsed = RequirementAgentOutput.model_validate(
        {
            "agent_name": "requirement",
            "cards": [
                {
                    "title": "幻觉卡",
                    "content": "引用不存在的物料",
                    "source_type": "email",
                    "confidence": 0.5,
                    "source_refs": [{"type": "part", "id": "PART-999"}],
                }
            ],
        }
    )
    run = AgentRun.objects.create(
        project=project,
        agent_name="requirement",
        status="needs_review",
        prompt_id=PROMPT_ID,
        prompt_version=PROMPT_VERSION,
        model="test-model",
        temperature=0,
        input_json={},
        input_hash="a" * 64,
        output_json=parsed.model_dump(mode="json"),
        output_schema_valid=True,
        reference_check_passed=None,
        invalid_references=[],
    )
    from agents import requirement as requirement_module

    monkeypatch.setattr(
        requirement_module.llm,
        "call_json",
        lambda *a, **k: llm.CallResult(parsed, "", None, 0.0, "json_object", agent_run=run),
    )
    document = Document.objects.get(doc_no="DOC-001")
    before = AgentRun.objects.count()
    summary = run_requirement_agent(project, document, seeded)
    assert summary["ok"] is False
    assert AgentRun.objects.count() == before  # 恰好 +0（update 不新增）
    run.refresh_from_db()
    assert run.status == "failed"
    assert run.reference_check_passed is False
    assert run.invalid_references  # 非空


# --- 增量 a：seed 文档 ↔ fixture 元数据一致性 -----------------------------
def test_seed_document_metadata_matches_fixture(seeded):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    by_no = {row["doc_no"]: row for row in fixture["documents"]}
    for doc_no in ("DOC-001", "DOC-002"):
        document = Document.objects.get(doc_no=doc_no)
        data = resolve_doc_path(document.file_path).read_bytes()
        real_hash = hashlib.sha256(data).hexdigest()
        assert document.checksum == by_no[doc_no]["checksum"] == real_hash
        assert document.size_bytes == by_no[doc_no]["size_bytes"] == len(data)


# --- T1 live（本机取证；沙箱 -m "not live" 跳过）--------------------------
@pytest.mark.live
def test_live_demo_email_end_to_end(seeded, project):
    document = Document.objects.get(doc_no="DOC-001")
    before_run = AgentRun.objects.count()
    before_req = Requirement.objects.count()
    before_link = TraceLink.objects.count()
    summary = run_requirement_agent(project, document, seeded)
    assert summary["ok"] is True
    assert summary["cards"] >= 5  # 固化：本机 3 次实测均 cards=5（D5-R2 收口）
    assert AgentRun.objects.count() == before_run + 1
    run = AgentRun.objects.get(pk=summary["agent_run_id"])
    assert run.status == "needs_review"
    assert run.reference_check_passed is True
    assert run.output_schema_valid is True
    for card in run.output_json.get("cards", []):
        assert card["priority"] in (None, "low", "medium", "high")
        assert card["source_type"] in ("prd", "sor", "email", "manual")
    assert Requirement.objects.count() == before_req
    assert TraceLink.objects.count() == before_link