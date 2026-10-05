"""Requirement Agent 生成管道（D5-R2 §2）。

``run_requirement_agent(project, document, user)``：读 Document 文件正文 → 渲染 prompt →
``call_json(RequirementAgentOutput)`` → 引用核验（§3）→ **同一 AgentRun 行**更新 →
返回摘要。一次运行 AgentRun **恰好 +1**（call_json 落一行；核验仅 update，不新增）。

- `call_json` 自身失败（SchemaInvalidError 等）已落 `failed` 行，管道**不重复写**；
- 核验通过 → `reference_check_passed=True`、`status` 保持 `needs_review`；
- 核验失败 → `reference_check_passed=False`、`status=failed`、`invalid_references` 落库、不进队列；
- **source_refs 策略**：LLM 为每卡输出结构化引用；系统在核验前**附加源文档引用作底**；两类都过同一核验器；
- `fake` 后端（`agent_run is None`）**不落库、不核验更新**（R1 边界）。
"""

from __future__ import annotations

from agents import llm
from agents.models import AgentRun
from agents.prompts import load, render_user_template
from agents.verification import verify_references
from config.settings import resolve_doc_path
from schemas.agent_outputs import RequirementAgentOutput

PROMPT_ID = "prompt.requirement.extract"
PROMPT_VERSION = "v1"
DEFAULT_MAX_TOKENS = 2048


class RequirementAgentError(Exception):
    """管道级错误（读文件 / prompt 装载等）。"""


def _read_document_text(document) -> str:
    path = resolve_doc_path(document.file_path)
    if not path.exists():
        raise RequirementAgentError(f"源文档文件不存在：{path}")
    if path.suffix.lower() == ".pdf":
        try:
            import pdfplumber
        except ImportError as exc:
            raise RequirementAgentError(
                "PDF 解析依赖 pdfplumber 未安装（登记延后）"
            ) from exc
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    return path.read_text(encoding="utf-8")


def run_requirement_agent(project, document, user, *, model=None, temperature=0):
    """执行 Requirement Agent，返回摘要 dict。"""

    content = _read_document_text(document)
    system, template = load(PROMPT_ID, PROMPT_VERSION)
    user_message = render_user_template(
        template,
        document_no=document.doc_no,
        doc_type=document.doc_type,
        title=document.title,
        content=content,
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]

    try:
        result = llm.call_json(
            RequirementAgentOutput,
            messages,
            PROMPT_ID,
            PROMPT_VERSION,
            temperature=temperature,
            max_tokens=DEFAULT_MAX_TOKENS,
            project=project,
            agent_name="requirement",
            model=model,
        )
    except llm.LLMError:
        # call_json 已落 failed 行；管道不重复写
        raise

    card_count = len(result.parsed.cards)
    run = result.agent_run
    if run is None:
        # fake 后端：不落库、不核验更新
        return {
            "ok": True,
            "fake": True,
            "agent_run_id": None,
            "cards": card_count,
            "summary": result.parsed.summary,
        }

    # source_refs 策略：LLM 输出引用 + 系统附加源文档引用作底
    refs = []
    for card in result.parsed.cards:
        refs.extend(card.source_refs or [])
    refs.append({"type": "document", "id": document.doc_no})

    invalid = verify_references(project.pk, refs)
    if invalid:
        payload = [
            {"entity_type": item.entity_type, "entity_id": item.entity_id, "reason": item.reason}
            for item in invalid
        ]
        AgentRun.objects.filter(pk=run.pk).update(
            reference_check_passed=False,
            status="failed",
            invalid_references=payload,
        )
        return {
            "ok": False,
            "agent_run_id": run.pk,
            "cards": card_count,
            "invalid_references": payload,
            "output": result.parsed.model_dump(mode="json"),
        }

    AgentRun.objects.filter(pk=run.pk).update(reference_check_passed=True)
    return {
        "ok": True,
        "agent_run_id": run.pk,
        "cards": card_count,
        "summary": result.parsed.summary,
        "output": result.parsed.model_dump(mode="json"),
    }