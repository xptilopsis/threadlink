from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import enum_choices
from schemas.agent_outputs import EntityType, LinkSource, TraceRelationType


class TraceLink(models.Model):
    """跨域追溯权威表（字典 §18、R3、PRD §6.1）。

    ``from_id`` / ``to_id`` 为源 / 目标实体的**业务编号**（R2，非数据库主键）。
    """

    project = models.ForeignKey(
        "core.Project", on_delete=models.CASCADE, related_name="trace_links"
    )
    from_type = models.CharField(max_length=32, choices=enum_choices(EntityType))
    from_id = models.CharField(max_length=64)
    to_type = models.CharField(max_length=32, choices=enum_choices(EntityType))
    to_id = models.CharField(max_length=64)
    relation_type = models.CharField(
        max_length=32, choices=enum_choices(TraceRelationType)
    )
    source = models.CharField(
        max_length=16, choices=enum_choices(LinkSource), default=LinkSource.MANUAL.value
    )
    confidence = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    agent_run = models.ForeignKey(
        "agents.AgentRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trace_links",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_trace_links",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    evidence = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_trace_links",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "project",
                    "from_type",
                    "from_id",
                    "to_type",
                    "to_id",
                    "relation_type",
                ],
                name="uq_tracelink_edge",
            ),
        ]
        indexes = [
            models.Index(
                fields=["project", "from_type", "from_id"],
                name="ix_tracelink_from",
            ),
            models.Index(
                fields=["project", "to_type", "to_id"], name="ix_tracelink_to"
            ),
            models.Index(
                fields=["project", "relation_type"], name="ix_tracelink_relation"
            ),
            models.Index(fields=["agent_run"], name="ix_tracelink_agent_run"),
            models.Index(fields=["confirmed_by"], name="ix_tracelink_confirmed_by"),
        ]

    def __str__(self):
        return f"{self.from_type}:{self.from_id} -{self.relation_type}-> {self.to_type}:{self.to_id}"
