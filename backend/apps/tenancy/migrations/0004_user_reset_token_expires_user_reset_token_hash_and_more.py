"""P4.7-T3 — password-reset fields on User + the Invitation table (RLS-aware).

The two User fields are covered by the existing user-table RLS (plain AddField). The new
`tenancy_invitation` table gets the same FORCE RLS + tenant-isolation policy as every
platform table (non-negotiable #6), so the non-superuser app role only ever sees its own
tenant's invitations.
"""
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models

_TABLE = "tenancy_invitation"
_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def apply_rls(apps, schema_editor):
    quser = f'"{settings.APP_DB_USER}"'
    with schema_editor.connection.cursor() as cur:
        cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{_TABLE}" TO {quser}')
        cur.execute(f'ALTER TABLE "{_TABLE}" ENABLE ROW LEVEL SECURITY')
        cur.execute(f'ALTER TABLE "{_TABLE}" FORCE ROW LEVEL SECURITY')
        cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{_TABLE}"')
        cur.execute(
            f'CREATE POLICY tenant_isolation ON "{_TABLE}" '
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def revert_rls(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{_TABLE}"')
        cur.execute(f'ALTER TABLE "{_TABLE}" NO FORCE ROW LEVEL SECURITY')
        cur.execute(f'ALTER TABLE "{_TABLE}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0003_user_is_tenant_admin"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="reset_token_expires",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="reset_token_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.CreateModel(
            name="Invitation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("email", models.EmailField(max_length=254)),
                ("name", models.CharField(blank=True, max_length=255)),
                ("grants", models.JSONField(blank=True, default=list)),
                ("token_hash", models.CharField(db_index=True, max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("accepted", "Accepted"),
                            ("revoked", "Revoked"),
                            ("expired", "Expired"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_invitations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="tenancy.tenant",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.RunPython(apply_rls, revert_rls),
    ]
