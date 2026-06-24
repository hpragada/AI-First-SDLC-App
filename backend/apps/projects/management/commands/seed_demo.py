"""`python manage.py seed_demo` (P0-T13) — seed the demo tenant/project/profile/specs.

Thin wrapper over `apps.projects.seed.seed_demo`; prints the ids you need to drive
the UI (paste the tenant id into the X-Tenant-ID field; use the user id at the gate).
"""
from django.core.management.base import BaseCommand

from apps.projects.seed import DEMO_USER_PASSWORD, seed_demo


class Command(BaseCommand):
    help = "Seed a demo tenant, user, project, profile, agent specs, and a work item."

    def handle(self, *args, **options):
        r = seed_demo()
        verb = "Created" if r.created else "Refreshed"
        self.stdout.write(self.style.SUCCESS(f"{verb} demo data:"))
        self.stdout.write(f"  tenant_id   : {r.tenant_id}   (paste into the UI's X-Tenant-ID)")
        self.stdout.write(f"  project_id  : {r.project_id}")
        self.stdout.write(f"  work_item_id: {r.work_item_id}")
        self.stdout.write(f"  user_id     : {r.user_id}   (approver at gates)")
        self.stdout.write(f"  user_email  : {r.user_email} / {DEMO_USER_PASSWORD}")
        self.stdout.write(f"  agent_specs : {r.agent_spec_count}")
        self.stdout.write(f"  connectors  : {r.connection_count}"
                          "  (docstore→confluence, tasktracker→jira)")
