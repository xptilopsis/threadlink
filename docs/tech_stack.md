# 技术栈（Tech Stack）

> 以下为锁定选型，除明确评审外不得随意更改。

## 语言与框架

- **Python 3.12**
- **Django 5.2 LTS**
- **Django Admin + HTMX**

## 数据库

- **开发库**：SQLite
- **演示/部署库**：PostgreSQL 16

> 不引入向量库 / RAG：D1-D11 不启用向量检索，相关依赖不进入锁定的技术栈。

## LLM

- **OpenAI SDK**

## 只读集成

- **Git（只读）**：GitPython，只允许 `log` / `show` / `diff` / `ls-tree`，禁止 `push` / `commit` / `checkout` / `reset`。
- **文件（只读）**：pdfplumber 解析，不写回源文件。

## 校验

- **Pydantic v2**

## 测试

- **pytest + pytest-django**

## 多租户与权限

- **单租户**：不建 `tenant_id`。
- **权限**：Django auth + `is_staff` / `superuser`，D11 再补简单对象权限，不做复杂 RBAC。

## Postgres（可选 compose）

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: threadlink
      POSTGRES_USER: threadlink
      POSTGRES_PASSWORD: threadlink
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```