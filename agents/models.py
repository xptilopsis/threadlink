from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import enum_choices
from schemas.agent_outputs import AgentName, AgentRunStatus


class AgentRun(models.Model):
    """LLM 调用审计（字典 §22、R1、interface_contract §6）。

    只对应实际发生的 LLM 调用；字段全集以 ``docs/interface_contract.md`` §6 与
    ``schemas/agent_outputs.py`` 为唯一权威。
    """

    project = models.ForeignKey(
        "core.Project", on_delete=models.CASCADE, related_name="agent_runs"
    )
    agent_name = models.CharField(max_length=32, choices=enum_choices(AgentName))
    status = models.CharField(max_length=16, choices=enum_choices(AgentRunStatus))
    prompt_id = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=32)
    model = models.CharField(max_length=64)
    temperature = models.DecimalField(max_digits=3, decimal_places=2)
    input_json = models.JSONField()
    input_hash = models.CharField(max_length=64)
    output_json = models.JSONField(null=True, blank=True)
    output_schema_valid = models.BooleanField(null=True, blank=True)
    reference_check_passed = models.BooleanField(null=True, blank=True)
    invalid_references = models.JSONField(null=True, blank=True)
    references = models.JSONField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_agent_runs",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(
                fields=["project", "agent_name", "status"],
                name="ix_agentrun_proj_agent_status",
            ),
        ]

    def __str__(self):
        return f"{self.agent_name}/{self.status} #{self.pk}"
