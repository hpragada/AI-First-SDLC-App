"""Connector catalog — the single source of truth for *which vendors* each capability
supports and *what fields* each vendor needs (P1 fix for Bugs.xlsx #39/#40).

Why this exists: the S-12 "Connect a capability" drawer used to show one hardcoded
Confluence-only form for every capability, and it saved the vendor's *display name*
("Confluence") as the connector — but `integrations/registry.py` is keyed by lowercase
slugs ("confluence"), so `test-connection` failed with
"No connector registered for docstore:Confluence." This catalog lists only the vendors
that are actually builder-wired (so a saved connection is always constructible) and
drives a per-vendor form on the frontend. Keep it in lockstep with `_BUILDERS` in
`integrations/registry.py` — a vendor here whose slug isn't registered there would
re-introduce that bug.

Field shape (consumed by the frontend to render inputs):
  {name, label, type: "text" | "password", placeholder, required}
`binding` fields are stored in `IntegrationConnection.scopes`; `secrets` fields are
write-only (encrypted, never returned).
"""
from __future__ import annotations


def _field(name: str, label: str, *, type: str = "text", placeholder: str = "",
           required: bool = True, hint: str = "") -> dict:
    return {"name": name, "label": label, "type": type,
            "placeholder": placeholder, "required": required, "hint": hint}


# capability -> {label, vendors: [{slug, label, no_secret?, binding[], secrets[]}]}.
# Only registered slugs appear here (see module docstring).
CONNECTOR_CATALOG: dict[str, dict] = {
    "docstore": {
        "label": "Documentation store",
        "vendors": [
            {
                "slug": "confluence",
                "label": "Confluence",
                "binding": [
                    _field("space_key", "Space key", placeholder="e.g. PAY"),
                    _field("base_url", "Base URL",
                           placeholder="https://acme.atlassian.net/wiki"),
                    _field("email", "Atlassian account email",
                           placeholder="you@acme.com",
                           hint="The account the API token belongs to — Atlassian auth is "
                                "email + token."),
                ],
                "secrets": [
                    _field("api_token", "API token", type="password",
                           placeholder="Paste token"),
                ],
            },
        ],
    },
    "tasktracker": {
        "label": "Task tracker",
        "vendors": [
            {
                "slug": "jira",
                "label": "Jira",
                "binding": [
                    _field("project_key", "Project key", placeholder="e.g. PAY"),
                    _field("base_url", "Base URL",
                           placeholder="https://acme.atlassian.net"),
                    _field("email", "Atlassian account email",
                           placeholder="you@acme.com",
                           hint="The account the API token belongs to — Atlassian auth is "
                                "email + token."),
                ],
                "secrets": [
                    _field("api_token", "API token", type="password",
                           placeholder="Paste token"),
                ],
            },
        ],
    },
    "designsource": {
        "label": "Design source",
        "vendors": [
            {
                "slug": "figma",
                "label": "Figma",
                "binding": [
                    _field("file_key", "File key", placeholder="e.g. aBcD1234"),
                ],
                "secrets": [
                    _field("access_token", "Access token", type="password",
                           placeholder="Paste token"),
                ],
            },
        ],
    },
    "codehost": {
        "label": "Code host",
        "vendors": [
            {
                "slug": "github",
                "label": "GitHub",
                "binding": [
                    # One code-host connection is tenant-wide: the token covers EVERY repo in
                    # the project, and each build targets its own work-item repo. So this is
                    # only an optional fallback default, not a per-repo binding — labelling it a
                    # required "Repository" read as single-repo on multi-repo projects (S.No 103).
                    _field("repo", "Default repository", placeholder="e.g. acme/payments",
                           required=False,
                           hint="Optional. Each build targets its own repo; this is only a "
                                "fallback default. The token must have access to ALL repos "
                                "in this project."),
                ],
                "secrets": [
                    _field("access_token", "Access token", type="password",
                           placeholder="Paste token (repo scope)"),
                ],
            },
        ],
    },
    "testmgmt": {
        "label": "Test management",
        "vendors": [
            {
                "slug": "xray",
                "label": "Xray",
                "binding": [
                    _field("project_key", "Project key", placeholder="e.g. PAY"),
                ],
                "secrets": [
                    _field("client_id", "Client ID", type="password",
                           placeholder="Paste client id"),
                    _field("client_secret", "Client secret", type="password",
                           placeholder="Paste client secret"),
                ],
            },
        ],
    },
    "codeintel": {
        "label": "Code intelligence",
        "vendors": [
            {
                "slug": "builtin",
                "label": "Built-in analyzer",
                "no_secret": True,   # local compute (git + filesystem) — no creds
                "binding": [],
                "secrets": [],
            },
        ],
    },
    "a11yai": {
        "label": "AI accessibility judgment",
        "vendors": [
            {
                # The platform's own judge — judgment runs through the ExecutionDriver, so
                # there is no model API key to store. A third-party accessibility-AI service
                # would be a second slug here, and no caller would change (#9).
                "slug": "builtin",
                "label": "Built-in judge",
                "no_secret": True,
                "binding": [],
                "secrets": [],
            },
        ],
    },
}


def catalog_payload() -> list[dict]:
    """The catalog as an ordered list for `GET /api/integrations/catalog/`."""
    return [
        {"capability": cap, "label": entry["label"], "vendors": entry["vendors"]}
        for cap, entry in CONNECTOR_CATALOG.items()
    ]


def vendor_label(capability: str, slug: str) -> str:
    """Human label for a stored connector slug (used by the read serializer). Falls back
    to the slug itself for anything not in the catalog."""
    for vendor in CONNECTOR_CATALOG.get(capability, {}).get("vendors", []):
        if vendor["slug"] == slug:
            return vendor["label"]
    return slug
