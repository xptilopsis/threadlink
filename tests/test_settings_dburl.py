"""D14-R2：settings.py 的 DATABASE_URL 解析三态（有 / 无 / 畸形）。

只验证 config.settings 对 DATABASE_URL 的解析分支，不改动任何运行时行为。
"""

import importlib

import pytest


@pytest.fixture
def load_settings(monkeypatch):
    """以指定 DATABASE_URL 重新加载 settings 模块，返回该模块对象。"""

    def _load(database_url):
        if database_url is None:
            monkeypatch.delenv("DATABASE_URL", raising=False)
        else:
            monkeypatch.setenv("DATABASE_URL", database_url)
        import config.settings as settings

        return importlib.reload(settings)

    yield _load
    # teardown：按还原后的环境重新加载，避免污染其它测试
    import config.settings as settings

    importlib.reload(settings)


def test_postgresql_url_overrides(load_settings):
    s = load_settings("postgresql://threadlink:threadlink@db:5432/threadlink")
    db = s.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["NAME"] == "threadlink"
    assert db["USER"] == "threadlink"
    assert db["PASSWORD"] == "threadlink"
    assert db["HOST"] == "db"
    assert db["PORT"] == "5432"


def test_postgres_scheme_alias(load_settings):
    s = load_settings("postgres://u:p@h:6543/n?sslmode=disable")
    db = s.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["NAME"] == "n"
    assert db["PORT"] == "6543"
    assert db["OPTIONS"] == {"sslmode": "disable"}


def test_missing_url_keeps_sqlite(load_settings):
    s = load_settings(None)
    db = s.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.sqlite3"
    assert str(db["NAME"]).endswith("db.sqlite3")


def test_root_relative_sqlite_url_not_hijacked(load_settings):
    # .env.example 里的缺省值形如 sqlite:///db.sqlite3 —— 必须保持 SQLite 路径不回归
    s = load_settings("sqlite:///db.sqlite3")
    db = s.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.sqlite3"
    assert str(db["NAME"]).endswith("db.sqlite3")


def test_malformed_postgres_url_is_tolerated(load_settings):
    # 畸形（缺 host/name）：不抛异常，仍走 postgres 引擎，字段为空
    s = load_settings("postgresql://")
    db = s.DATABASES["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["NAME"] == ""
    assert db["HOST"] == ""