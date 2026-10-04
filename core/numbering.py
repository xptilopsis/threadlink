"""业务编号生成器与 ``NumberedModel`` mixin（ADR-0006 / ADR-0007）。

约定（ADR-0006）：

- 编号格式 ``<prefix><NNN>``，三位零填充；超过 999 自然进位（不截断）。
- 作用域为 project 级；多数实体直接持 ``project`` FK，间接归属实体
  （如 ``BomItem`` 经 ``bom.project``）由模型覆写 ``number_scope_filter`` 解析。
- 唯一性两层级保证：应用层生成 + 数据库 ``UniqueConstraint`` 兜底。
- 自动生成遇唯一冲突重试 ``MAX_RETRIES`` 次，耗尽抛 ``NumberingError``。
- 人工显式编号不做自动生成，仅做唯一性预检。
- 导入路径（fixture 回填）显式直写编号，或用 ``numbering_suspended()``
  临时关闭自动生成。
"""

from __future__ import annotations

import re
from contextlib import contextmanager

from django.db import IntegrityError, models, transaction

_NUMBER_SUFFIX = re.compile(r"(\d+)$")
MAX_RETRIES = 3
DEFAULT_WIDTH = 3

_suspended = False


class NumberingError(Exception):
    """业务编号生成 / 唯一性校验失败。"""


@contextmanager
def numbering_suspended():
    """临时关闭自动编号生成（导入路径用），退出时恢复原状态。"""

    global _suspended
    previous = _suspended
    _suspended = True
    try:
        yield
    finally:
        _suspended = previous


def is_suspended() -> bool:
    return _suspended


def next_number(
    project,
    prefix: str,
    model,
    field_name: str,
    scope_filter: dict | None = None,
    width: int = DEFAULT_WIDTH,
) -> str:
    """解析 ``(project, 编号字段)`` 现有最大值并 +1，返回零填充编号。

    ``scope_filter`` 用于间接归属实体（如 ``{"bom__project": project}``）；
    默认按 ``{"project": project}`` 过滤。
    """

    queryset = model._default_manager.all()
    if scope_filter is None:
        queryset = queryset.filter(project=project)
    else:
        queryset = queryset.filter(**scope_filter)

    max_index = 0
    for value in queryset.values_list(field_name, flat=True):
        if not value or not value.startswith(prefix):
            continue
        match = _NUMBER_SUFFIX.search(value)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return f"{prefix}{max_index + 1:0{width}d}"


class NumberedModel(models.Model):
    """业务编号模型基类：字段为空则按 project 作用域自动生成。"""

    number_field: str | None = None
    number_prefix: str | None = None

    class Meta:
        abstract = True

    def number_scope_project(self):
        return getattr(self, "project", None)

    def number_scope_filter(self, project) -> dict:
        return {"project": project}

    def _manual_number_conflicts(self, field_name: str) -> bool:
        project = self.number_scope_project()
        if project is None:
            return False
        queryset = type(self)._default_manager.filter(
            **self.number_scope_filter(project),
            **{field_name: getattr(self, field_name)},
        )
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)
        return queryset.exists()

    def save(self, *args, **kwargs):
        field_name = self.number_field
        if field_name and not _suspended:
            current = getattr(self, field_name, None)
            if current:
                if self._manual_number_conflicts(field_name):
                    raise NumberingError(
                        f"{type(self).__name__}.{field_name}={current!r} "
                        f"在项目内已存在（业务编号唯一）"
                    )
                return super().save(*args, **kwargs)

            project = self.number_scope_project()
            if project is None:
                raise NumberingError(
                    f"{type(self).__name__}.{field_name} 缺少 project 作用域，无法自动编号"
                )
            scope_filter = self.number_scope_filter(project)
            last_error = None
            for _ in range(MAX_RETRIES):
                generated = next_number(
                    project,
                    self.number_prefix,
                    model=type(self),
                    field_name=field_name,
                    scope_filter=scope_filter,
                )
                setattr(self, field_name, generated)
                try:
                    with transaction.atomic():
                        return super().save(*args, **kwargs)
                except IntegrityError as exc:
                    last_error = exc
                    setattr(self, field_name, None)
            raise NumberingError(
                f"{type(self).__name__}.{field_name} 自动编号重试 {MAX_RETRIES} 次仍冲突"
            ) from last_error
        return super().save(*args, **kwargs)