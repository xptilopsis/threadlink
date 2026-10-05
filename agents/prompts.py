"""Prompt 装载器（D5-R2 §1）。

``load(prompt_id, version)`` → ``(system, user_template)``；文件缺失 **fail-loud**（含缺失路径）。
``render_user_template`` 注入源文档正文与业务编号。

``prompt_id`` → 目录映射：契约 ``prompt.requirement.extract`` 对应 ``prompts/requirement_agent/<version>/``。
``schema.json`` 为**参考件**，权威 schema = ``schemas/agent_outputs.py``（Pydantic 派生）。
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

PROMPTS_ROOT = Path(settings.BASE_DIR) / "prompts"

PROMPT_DIRS = {
    "prompt.requirement.extract": "requirement_agent",
}


class PromptNotFoundError(Exception):
    """prompt 目录/文件缺失（fail-loud）。"""


def load(prompt_id: str, version: str = "v1"):
    dir_name = PROMPT_DIRS.get(prompt_id)
    if dir_name is None:
        raise PromptNotFoundError(f"未知 prompt_id：{prompt_id!r}（无目录映射）")
    base = PROMPTS_ROOT / dir_name / version
    system_path = base / "system.md"
    user_path = base / "user_template.md"
    for path in (system_path, user_path):
        if not path.exists():
            raise PromptNotFoundError(f"缺少 prompt 文件：{path}")
    return (
        system_path.read_text(encoding="utf-8"),
        user_path.read_text(encoding="utf-8"),
    )


def render_user_template(
    template: str, *, document_no: str, doc_type: str, title: str, content: str
) -> str:
    """注入源文档业务编号与正文（用 replace，避免正文中 `{}` 触发 format 异常）。"""

    return (
        template.replace("{document_no}", str(document_no))
        .replace("{doc_type}", str(doc_type))
        .replace("{title}", str(title))
        .replace("{content}", content)
    )