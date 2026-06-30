"""Tenancy: Tenant (RLS root), custom User, Membership."""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from apps.base import Role, TenantScopedModel, UUIDModel


class Tenant(UUIDModel):
    """RLS root. `tenant_id` mirrors `id` so the uniform RLS policy applies here too."""

    tenant_id = models.UUIDField(editable=False, db_index=True)
    name = models.CharField(max_length=255)
    config = models.JSONField(default=dict, blank=True)
    model_routing = models.JSONField(default=dict, blank=True)

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            self.tenant_id = self.id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, name, tenant, password=None, **extra):
        if not email:
            raise ValueError("Users require an email.")
        if tenant is None:
            raise ValueError("Users are tenant-scoped; a tenant is required.")
        user = self.model(email=self.normalize_email(email), name=name, tenant=tenant, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, tenant, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, name, tenant, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, UUIDModel):
    """Email-login user, tenant-scoped (carries `tenant_id`)."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="users")
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    # Tenant-level admin (no project) — manages users/roles/integrations tenant-wide
    # (DECISION-1). Set True for the first user created by self-serve signup (P4.7-T2).
    is_tenant_admin = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    def __str__(self) -> str:
        return self.email


class Membership(TenantScopedModel):
    """Binds a User to a Project with a Role."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=32, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "project", "role"], name="uniq_user_project_role"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.project_id}:{self.role}"
