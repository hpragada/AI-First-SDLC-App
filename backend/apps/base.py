"""Shared abstract model bases + cross-app enums.

Non-negotiable #6: every platform table carries `tenant_id` and (in P0-T4) an RLS
policy. `TenantScopedModel` supplies the `tenant_id` column via a FK; `Tenant`
itself mirrors its own id into `tenant_id` so the same RLS policy applies uniformly.
"""
import uuid

from django.db import models


class UUIDModel(models.Model):
    """uuid pk + created/updated timestamps (spec §1 universal columns)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantScopedModel(UUIDModel):
    """Adds the `tenant_id` column (FK) that RLS keys on."""

    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
    )

    class Meta:
        abstract = True


class Role(models.TextChoices):
    """Membership / Approval roles (spec §1)."""

    PRODUCT_OWNER = "product_owner", "Product Owner"
    ARCHITECT = "architect", "Architect"
    DESIGNER = "designer", "Designer"
    TECH_LEAD = "tech_lead", "Tech Lead"
    ENGINEER = "engineer", "Engineer"
    REVIEWER = "reviewer", "Reviewer"
    QA_LEAD = "qa_lead", "QA Lead"
    SECURITY_ENGINEER = "security_engineer", "Security Engineer"
    DEVOPS = "devops", "DevOps"
    ADMIN = "admin", "Admin"
