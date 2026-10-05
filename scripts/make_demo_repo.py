"""确定性演示 Git 仓库生成脚本（D4-R2 Step 1）。

- 输出 ``.data/demo-repo``（``.data/`` 在 .gitignore，禁止提交其内容）。
- 确定性：文件内容 LF 原样写入；git 调用带 ``-c core.autocrlf=false
  -c commit.gpgsign=false``；author/committer 姓名/邮箱/时间（ISO8601+时区）全部固定；
  生成 3 个 commit，其 author 邮箱 / message 主题与 fixtures ``git_commits`` 呼应
  （author_name 取 ASCII 以保证跨机字节确定性，回填 step 会对齐）。
- 已存在默认拒绝覆盖（``--force`` 重建）。
- ``--check``：比对 ``.data/demo-repo`` 现有 3 个 SHA 与 fixtures 当前值，不一致打印 diff
  并以退出码 1 结束。

用法：
    python scripts/make_demo_repo.py
    python scripts/make_demo_repo.py --force
    python scripts/make_demo_repo.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPO = BASE_DIR / ".data" / "demo-repo"
FIXTURE = BASE_DIR / "fixtures" / "demo_seed.json"

COMMITS = [
    {
        "files": {"power/README.md": "support 9-36V wide input\n"},
        "message": "feat(power): support 9-36V wide input",
        "author_name": "RD Engineer",
        "author_email": "rd@threadlink.example.com",
        "date": "2026-02-21T14:30:00+08:00",
    },
    {
        "files": {"bom/selection.csv": "PART-002,6A\n"},
        "message": "fix(bom): replace obsolete DC-DC with 6A module",
        "author_name": "RD Engineer",
        "author_email": "rd@threadlink.example.com",
        "date": "2026-02-21T14:45:00+08:00",
    },
    {
        "files": {"test/ip65.md": "IP65 enclosure validation\n"},
        "message": "test(env): add IP65 enclosure validation",
        "author_name": "Test Engineer",
        "author_email": "tester@threadlink.example.com",
        "date": "2026-03-02T16:20:00+08:00",
    },
]


def _git(args, cwd, env=None, check=True):
    base = ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false"]
    return subprocess.run(
        base + args,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=check,
    )


def _commit_env(spec):
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": spec["author_name"],
            "GIT_AUTHOR_EMAIL": spec["author_email"],
            "GIT_COMMITTER_NAME": spec["author_name"],
            "GIT_COMMITTER_EMAIL": spec["author_email"],
            "GIT_AUTHOR_DATE": spec["date"],
            "GIT_COMMITTER_DATE": spec["date"],
        }
    )
    return env


def _on_rm_error(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def shas(repo: Path):
    if not (repo / ".git").exists():
        return None
    out = _git(["log", "--format=%H", "--reverse"], repo).stdout.strip().splitlines()
    return out


def generate(repo: Path, force: bool):
    if repo.exists():
        if not force:
            raise SystemExit(f"[FAIL] {repo} 已存在；如需重建请加 --force")
        shutil.rmtree(repo, onerror=_on_rm_error)
    repo.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], repo)
    for spec in COMMITS:
        for rel, content in spec["files"].items():
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode("utf-8"))  # LF 原样
        _git(["add", "-A"], repo)
        _git(["commit", "-q", "-m", spec["message"]], repo, env=_commit_env(spec))
    return shas(repo)


def main(argv=None):
    parser = argparse.ArgumentParser(description="确定性演示 Git 仓库生成")
    parser.add_argument("--repo", default=str(DEFAULT_REPO))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    repo = Path(args.repo)

    if args.check:
        generated = shas(repo)
        if generated is None:
            print(f"[FAIL] {repo} 不存在，无法自检；请先运行 make_demo_repo.py")
            return 1
        fixture_shas = [
            row["sha"]
            for row in json.loads(FIXTURE.read_text(encoding="utf-8"))["git_commits"]
        ]
        if generated == fixture_shas:
            print("[OK] 生成 SHA 与 fixtures 完全一致（确定性通过）")
            for sha in generated:
                print(f"  {sha}")
            return 0
        print("[FAIL] SHA 不一致：")
        width = max(len(generated), len(fixture_shas))
        for i in range(width):
            gen = generated[i] if i < len(generated) else "(none)"
            fix = fixture_shas[i] if i < len(fixture_shas) else "(none)"
            print(f"  commit{i + 1} {'==' if gen == fix else '!='} generated={gen} fixture={fix}")
        return 1

    generated = generate(repo, args.force)
    print(f"[OK] 已生成 {repo}")
    for i, sha in enumerate(generated, 1):
        print(f"  commit{i}: {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())