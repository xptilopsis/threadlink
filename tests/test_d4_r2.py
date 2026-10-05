"""D4-R2：确定性 demo 仓库 + 只读同步 + 只读 Admin 验收测试。

前置：``.data/demo-repo`` 须先由 ``scripts/make_demo_repo.py`` 生成（本测试对
缺失仓库整体 skip，避免污染其它机器）。数据由 ``load_demo_seed --flush`` 提供，
其 GitCommit 的 SHA 与仓库一致（0/0/0 幂等）。
"""

import subprocess
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Document, GitCommit, GitRepo, User

BASE_DIR = Path(settings.BASE_DIR)
DEMO_REPO = BASE_DIR / ".data" / "demo-repo"

pytestmark = pytest.mark.skipif(
    not DEMO_REPO.exists(),
    reason="需先运行 scripts/make_demo_repo.py 生成 .data/demo-repo",
)


@pytest.fixture
def seeded(db):
    call_command("load_demo_seed", flush=True, verbosity=0)
    return User.objects.get(username="admin")


# --- 1) roots 白名单 -------------------------------------------------------
def test_sync_fail_closed_without_roots(seeded, monkeypatch):
    monkeypatch.delenv("GIT_READONLY_ROOTS", raising=False)
    with pytest.raises(CommandError):
        call_command("sync_git_repo")


def test_sync_rejects_repo_outside_roots(seeded, monkeypatch):
    monkeypatch.setenv("GIT_READONLY_ROOTS", "docs")  # .data 不在白名单
    with pytest.raises(CommandError):
        call_command("sync_git_repo")


# --- 2) 幂等 + fail-loud ---------------------------------------------------
def test_sync_idempotent(seeded, monkeypatch, capsys):
    monkeypatch.setenv("GIT_READONLY_ROOTS", ".data")
    call_command("sync_git_repo")
    first = capsys.readouterr().out
    assert "added=0" in first and "updated=0" in first and "missing=0" in first

    call_command("sync_git_repo")
    second = capsys.readouterr().out
    assert "added=0" in second and "updated=0" in second and "missing=0" in second


def test_sync_missing_is_fail_loud(seeded, monkeypatch, capsys):
    monkeypatch.setenv("GIT_READONLY_ROOTS", ".data")
    commit = GitCommit.objects.order_by("id").first()
    original = commit.sha
    commit.sha = "0" * 40
    commit.save(update_fields=["sha"])

    with pytest.raises(CommandError):
        call_command("sync_git_repo")
    out = capsys.readouterr().out
    assert "missing=1" in out
    assert "0" * 40 in out

    # sync 期间为 original 新建了一行；先清理再恢复本行（用例结束事务回滚兜底）
    GitCommit.objects.filter(repo=commit.repo, sha=original).exclude(
        pk=commit.pk
    ).delete()
    commit.sha = original
    commit.save(update_fields=["sha"])


# --- 3) AC-008：同步不改动仓库 --------------------------------------------
def _snapshot():
    head = subprocess.run(
        ["git", "-C", str(DEMO_REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(DEMO_REPO), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    mtimes = {
        str(path.relative_to(DEMO_REPO)): path.stat().st_mtime_ns
        for path in sorted(DEMO_REPO.rglob("*"))
        if path.is_file()
    }
    return head, status, mtimes


def test_sync_does_not_mutate_repo(seeded, monkeypatch):
    monkeypatch.setenv("GIT_READONLY_ROOTS", ".data")
    before = _snapshot()
    call_command("sync_git_repo")
    after = _snapshot()
    assert before[0] == after[0]  # HEAD 不变
    assert before[1] == "" and after[1] == ""  # status --porcelain 为空
    assert before[2] == after[2]  # 工作树文件 mtime 不变


# --- 4) Admin 只读 ---------------------------------------------------------
def test_readonly_admin_pages(seeded, client):
    client.force_login(seeded)
    for url in (
        "/admin/core/document/",
        "/admin/core/gitrepo/",
        "/admin/core/gitcommit/",
    ):
        assert client.get(url).status_code == 200, url


def test_readonly_admin_add_forbidden(seeded, client):
    client.force_login(seeded)
    for url in (
        "/admin/core/document/add/",
        "/admin/core/gitrepo/add/",
        "/admin/core/gitcommit/add/",
    ):
        assert client.get(url).status_code == 403, url


def test_readonly_admin_detail_visible_post_forbidden(seeded, client):
    client.force_login(seeded)
    document = Document.objects.order_by("id").first()
    change_url = f"/admin/core/document/{document.pk}/change/"
    assert client.get(change_url).status_code == 200
    assert client.post(change_url, {}).status_code == 403


# --- 5) 计数回归 -----------------------------------------------------------
def test_counts_regression(seeded):
    assert GitRepo.objects.count() == 1
    assert GitCommit.objects.count() == 3
    assert Document.objects.count() == 5