"""``sync_git_repo``：从只读 Git 仓库同步 ``GitCommit``（D4-R2 Step 3）。

语义（以仓库为准的 upsert，fail-loud，不静默删）：

- 仓库有 / DB 无 → 新增 ``GitCommit`` 行；
- 两侧都有 → 以仓库为准更新 metadata（message / author / committed_at）；
- DB 有 / 仓库无 → 列出明细并以退出码 1 结束（这些行可能被 TraceLink 引用，禁止自动清理）；
- 输出统计 ``added`` / ``updated`` / ``missing``。

安全：

- 路径 ``GitRepo.local_path`` 相对 ``BASE_DIR`` 解析；白名单 ``GIT_READONLY_ROOTS``
  （``os.pathsep`` 分隔，亦相对 ``BASE_DIR``）经 ``realpath`` 前缀校验，防 ``../`` 逃逸；
- 未配置 roots → **fail-closed**（拒绝执行并提示）；
- 只读：仅使用 ``git log`` 类读取，命令不改变仓库状态。

注：``GitCommit`` 模型无 ``files_changed`` 字段（字典 §21），故本命令不落该列。
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from core.models import GitCommit, GitRepo

BASE_DIR = Path(settings.BASE_DIR)


def _resolve_under_base(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def _readonly_roots() -> list[Path]:
    raw = os.environ.get("GIT_READONLY_ROOTS", "")
    return [_resolve_under_base(part) for part in raw.split(os.pathsep) if part.strip()]


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([str(path), str(root)]) == str(root)
    except ValueError:
        return False


def _git_log(repo_path: Path):
    result = subprocess.run(
        ["git", "-C", str(repo_path), "log", "--format=%H|%an|%ae|%aI|%s"],
        capture_output=True,
        text=True,
        check=True,
    )
    rows = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        sha, author_name, author_email, iso, subject = line.split("|", 4)
        rows.append(
            {
                "sha": sha,
                "author_name": author_name,
                "author_email": author_email,
                "committed_at": parse_datetime(iso),
                "message": subject,
            }
        )
    return rows


class Command(BaseCommand):
    help = "从只读 Git 仓库同步 GitCommit（upsert，fail-loud，不静默删）。"

    def add_arguments(self, parser):
        parser.add_argument("--repo", help="仅同步指定 GitRepo.name")

    def handle(self, *args, **options):
        roots = _readonly_roots()
        if not roots:
            raise CommandError(
                "未配置 GIT_READONLY_ROOTS（os.pathsep 分隔；Windows 用分号 ';'）；"
                "拒绝执行（fail-closed）"
            )

        repos = GitRepo.objects.all()
        if options.get("repo"):
            repos = repos.filter(name=options["repo"])

        added = updated = 0
        missing = []
        for repo in repos:
            repo_path = _resolve_under_base(repo.local_path)
            if not any(_is_within(repo_path, root) for root in roots):
                raise CommandError(
                    f"仓库路径 {repo_path} 不在 GIT_READONLY_ROOTS 白名单内，拒绝执行"
                )
            if not (repo_path / ".git").exists():
                raise CommandError(f"仓库路径不存在或非 Git 仓库：{repo_path}")

            real_commits = _git_log(repo_path)
            real_shas = {row["sha"] for row in real_commits}
            existing = {obj.sha: obj for obj in GitCommit.objects.filter(repo=repo)}

            for row in real_commits:
                obj = existing.get(row["sha"])
                if obj is None:
                    GitCommit.objects.create(
                        repo=repo,
                        project=repo.project,
                        sha=row["sha"],
                        author_name=row["author_name"],
                        author_email=row["author_email"],
                        committed_at=row["committed_at"],
                        message=row["message"],
                        branch=repo.default_branch or "",
                    )
                    added += 1
                    continue
                changed = (
                    obj.message != row["message"]
                    or obj.author_name != row["author_name"]
                    or obj.author_email != row["author_email"]
                    or obj.committed_at != row["committed_at"]
                )
                if changed:
                    obj.message = row["message"]
                    obj.author_name = row["author_name"]
                    obj.author_email = row["author_email"]
                    obj.committed_at = row["committed_at"]
                    obj.save(
                        update_fields=[
                            "message",
                            "author_name",
                            "author_email",
                            "committed_at",
                        ]
                    )
                    updated += 1

            for sha in existing:
                if sha not in real_shas:
                    missing.append(f"  {repo.name}: {sha}（DB 有、仓库无）")

        self.stdout.write(f"added={added} updated={updated} missing={len(missing)}")
        if missing:
            self.stdout.write("missing 明细：")
            for line in missing:
                self.stdout.write(line)
            raise CommandError(
                "存在 DB 有而仓库无的 GitCommit（可能被 TraceLink 引用，禁止自动清理）"
            )