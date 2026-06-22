"""Ledger: append-only Event stream (provenance/events — #3)."""
from django.db import models

from apps.base import TenantScopedModel


class AppendOnlyError(Exception):
    """Raised on any attempt to mutate or delete a persisted Event."""


class Event(TenantScopedModel):
    """Append-only. App-level guard here; a DB-level guard is added in P0-T4."""

    actor = models.CharField(max_length=255)
    action = models.CharField(max_length=128)
    target_type = models.CharField(max_length=64)
    target_id = models.UUIDField(null=True, blank=True)
    ts = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["ts"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("Event rows are append-only; updates are not allowed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Event rows are append-only; deletes are not allowed.")

    def __str__(self) -> str:
        return f"{self.actor} {self.action} {self.target_type}:{self.target_id}"
