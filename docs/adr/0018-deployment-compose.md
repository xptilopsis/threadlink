# ADR-0018：Docker Compose 部署（演示级）

- **状态**：已接受（D14-R2）
- **日期**：2026-10-16
- **前置**：D14-R1 全系统独立复检（受限）；D14-R2 Step 1
- **范围声明**：本 ADR 描述**演示级**容器化部署；**本轮不在容器内跑 pytest、不验证 LLM / live**——Postgres 是部署目标，GT 分层仍以 SQLite 运行（ADR-0008 既定）。

## 1. 背景与目标

ThreadLink 开发与验收路径基于 SQLite（`db.sqlite3`，仓库根）。部署目标需与生产形态接近的数据库（Postgres）。本轮引入 `docker compose` 提供「一条命令起服务」的演示路径，**不改变**既有 SQLite 开发路径（默认零变化）。

## 2. 拓扑

```
宿主机 (.env: POSTGRES_* / DJANGO_*)
   │
   ├── db  : pgvector/pgvector:pg16   ← 卷 pgdata（数据持久化）
   │        healthcheck: pg_isready
   │
   └── web : build . (python:3.12-slim + git)
            depends_on: db(healthy)
            ports 8000:8000（占用时改 8001:8000）
            环境：DJANGO_DEBUG / DJANGO_ALLOWED_HOSTS / DJANGO_SECRET_KEY 透传
                  DATABASE_URL **强制** postgresql://threadlink:threadlink@db:5432/threadlink
                  GIT_READONLY_ROOTS=.data
            卷：./.data:/app/.data、./documents/uploads:/app/documents/uploads
            command: python manage.py runserver 0.0.0.0:8000
```

## 3. DATABASE_URL 解析（`config/settings.py`，仅此一处变更）

- 存在且以 `postgresql://` 或 `postgres://` 开头 → 覆盖 `DATABASES['default']` 为 `django.db.backends.postgresql`；
- **缺省 / 其他值（含 `.env.example` 的 `sqlite:///db.sqlite3`）→ 现有 SQLite 逻辑零变化**；
- 解析用 `urllib.parse`（`urlparse` + `parse_qs` + `unquote`）手写，**零新依赖**（`psycopg[binary]` 已在 `requirements/base.txt`）；
- 查询串（如 `?sslmode=disable`）映射到 `OPTIONS`；畸形 URL（如 `postgresql://`）**不抛异常**，字段留空。
- 单测：`tests/test_settings_dburl.py`（有 / 别名 `postgres://` / 无 / SQLite 值不回归 / 畸形 五态）。

**为何强制覆盖**：宿主 `.env` 的 `DATABASE_URL` 常为 SQLite 值；若透传，容器内 web 会去连容器内 SQLite 文件而非 `db` 服务。故 compose 中**硬编码** 容器内 Postgres URL，不引用 `${DATABASE_URL}`。

## 4. 关键取舍

| 取舍 | 选择 | 理由 |
| --- | --- | --- |
| 镜像 `pgvector/pgvector:pg16` | 采用 | 能力预留（未来向量检索）；**本轮无向量表、未启用任何扩展** |
| `runserver` 而非 gunicorn | 采用 | 演示级，零额外依赖与配置；**生产化（静态文件 / 反向代理 / HTTPS）→ v2** |
| 容器内不跑 pytest | 采用 | 本轮范围：部署路径验证；测试分层仍以宿主 SQLite 运行（ADR-0008） |
| `git config --global --add safe.directory '*'` | 采用 | bind mount 属主与容器用户不一致会被 git 拒绝（已知坑） |
| `.data` / `documents/uploads` 走卷 | 采用 | 跨环境 SHA 一致性（宿主生成、容器读取）+ 上传产物持久化；**不进镜像**（`.dockerignore`） |

## 5. 验证边界（截至 Step 1 撰写时点）

**本步（Step 1）已验证**（宿主，无 docker 命令）：
- `tests/test_settings_dburl.py` 五态单测通过；
- `pytest -q -m "not live"` 全绿（不回归）；
- `manage.py check` / `makemigrations --check --dry-run` = No changes；
- YAML 语法探测（见 §6）。

**待 Docker 验证（R2 闭环条件 —— 未完成前 R2 不闭环）**：
1. `docker compose config`（YAML/变量插值合法性）；
2. `docker compose up -d --build` → `compose ps`：db healthy、web up（首次构建 5–15 min 属正常）；
3. `scripts/compose_bootstrap.ps1` 全链：migrate → createsuperuser → load_demo_seed → `make_demo_repo --check` → `sync_git_repo` **0/0/0**（跨环境 SHA 一致性实证）→ 22 集合断言；
4. `scripts/compose_smoke.ps1`：认证态 `/admin/` 200 + `/trace/serial/SN-DEMO-001/?format=json` 200 且 31 nodes / 37 edges；
5. 宿主 `pytest -q -m "not live"` 不回归；
6. `down`（保留卷）→ `up -d` → 22 集合复断（数据存活）。

> **环境阻塞记录**：执行本步时宿主**未安装 Docker**（`docker` 在 bash/PowerShell 均不可用；`C:\Program Files\Docker`、`C:\ProgramData\DockerDesktop` 不存在）→ 上述 6 项**均未执行**，需人工安装后再续（Step 2/3）。

## 6. 轻验证（YAML 语法）

- 探测 `python -c "import yaml"`：可用 → 对 `docker-compose.yml` 做解析检查；不可用 → 跳过（**不安装新依赖**）并标注「待 `docker compose config`」。结果见 R2 汇报。

## 7. 已知缺口（→ v2）

1. 无 gunicorn / 静态文件服务 / HTTPS 终止 / 反向代理；
2. 无镜像层缓存优化（每次全量 pip 安装）；
3. 无健康检查 on web（仅 db）；
4. 无 CI 集成（容器内跑测试）；
5. pgvector 能力仅预留，未建向量列/索引。

## 8. 与既有路径的关系

- **SQLite 开发路径不变**：不设 `DATABASE_URL`（或设为 sqlite 值）时行为与 D14-R1 完全一致；
- **GT 分层不变**：`@pytest.mark.live` / `transport` 与 `not live` 套件仍在宿主运行；
- 演示恢复脚本（`scripts/demo_reset.ps1`）与容器路径**相互独立**：容器路径用 `compose_bootstrap.ps1`。