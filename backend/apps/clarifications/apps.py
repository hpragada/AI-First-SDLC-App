from django.apps import AppConfig


class ClarificationsConfig(AppConfig):
    """Clarifications — the control-plane interactive Q&A channel (req #2).

    An agent's question becomes a control-plane object (a sibling of Approval), surfaced
    and answered in the web app. The engine never blocks on a human inside a hook (#2) —
    it waits on a tool result while the model is idle (zero token cost), and the answer is
    recorded here, out of band."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.clarifications"
