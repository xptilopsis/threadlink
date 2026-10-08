#!/usr/bin/env python
"""D13-R1：演示用「邮件 → 需求卡」一次性触发脚本。

``requirement`` Agent **没有 management command**，只暴露 HTTP 端点；本脚本提供命令行等价入口，
供 ``scripts/demo_reset.ps1`` 第 7 步（生成线：requirement → run 8）与本地演示直接调用。

用法::

    .venv\\Scripts\\python.exe scripts\\run_requirement_demo.py
    .venv\\Scripts\\python.exe scripts\\run_requirement_demo.py --project DEMO-GW --document DOC-001 --username admin

仅调用 ``run_requirement_agent``（真实 LLM，产生 1 条 ``needs_review`` AgentRun）；**不写实体**。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from agents.requirement import run_requirement_agent  # noqa: E402
from core.models import Document, Project, User  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="演示：运行 Requirement Agent（邮件/PRD → 需求卡，needs_review）"
    )
    parser.add_argument("--project", default="DEMO-GW")
    parser.add_argument("--document", default="DOC-001")
    parser.add_argument("--username", default="admin")
    args = parser.parse_args(argv)

    project = Project.objects.filter(code=args.project).first()
    if project is None:
        print(f"[FAIL] project 不存在：{args.project}")
        return 1
    document = Document.objects.filter(project=project, doc_no=args.document).first()
    if document is None:
        print(f"[FAIL] document 不存在：{args.document}")
        return 1
    user = User.objects.filter(username=args.username).first()
    if user is None:
        print(f"[FAIL] user 不存在：{args.username}")
        return 1

    try:
        summary = run_requirement_agent(project, document, user)
    except Exception as exc:  # noqa: BLE001 —— 以明确 FAIL 呈现，退出码非 0
        print(f"[FAIL] requirement 运行失败：{exc}")
        return 1

    print(
        f"requirement ok={summary.get('ok')} run={summary.get('agent_run_id')} "
        f"cards={summary.get('cards')}"
    )
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())