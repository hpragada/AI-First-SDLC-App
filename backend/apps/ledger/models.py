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

    # Which project and work item this event belongs to (Bugs S.No 230).
    #
    # The row used to record only WHAT KIND of thing something happened to and that thing's id.
    # With no link to a project, the agent briefing's recent-events list could not be scoped and
    # so was scoped to the whole workspace — handing every run the last 20 events from every
    # project the tenant has ever worked on, including questions asked on work items it has never
    # seen, from runs that were since deleted.
    #
    # Plain ids rather than foreign keys, deliberately: the ledger outlives what it describes.
    # A CASCADE would delete history when a project is removed and a PROTECT would stop the
    # project being removed at all — both wrong for an append-only record of what happened.
    #
    # Nullable, and not backfilled: rows written before this existed carry no project, so they
    # fall out of a project-scoped briefing — which is the outcome we want, not data loss.
    # `Event` is append-only by design (see `save` below), so a backfill would have to bypass the
    # guard, and there is no reason to take that risk for events nothing should be reading.
    project_id = models.UUIDField(null=True, blank=True, db_index=True)
    work_item_id = models.UUIDField(null=True, blank=True, db_index=True)

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
