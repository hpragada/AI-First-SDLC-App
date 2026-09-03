"""Signed Git-webhook endpoint (Phase-2 §7).

`POST /api/webhooks/github/<tenant_id>/` — GitHub can only set the URL + a shared secret, so the
tenant is carried in the path and the **raw body** is HMAC-verified against the platform's
webhook secret before anything in the payload is trusted. Verified deliveries are deduped +
reconciled by `integrations.webhooks`. No DRF auth/permission classes run — the signature *is*
the authentication.
"""
from __future__ import annotations

import json

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.webhooks import reconcile_github, verify_github_signature


class GithubWebhookView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, tenant_id):
        body: bytes = request.body
        signature = request.headers.get("X-Hub-Signature-256")
        secret = getattr(settings, "GITHUB_WEBHOOK_SECRET", "")
        if not verify_github_signature(secret, body, signature):
            return Response({"detail": "invalid signature"},
                            status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return Response({"detail": "malformed payload"},
                            status=status.HTTP_400_BAD_REQUEST)

        out = reconcile_github(
            tenant_id=str(tenant_id),
            event=request.headers.get("X-GitHub-Event", ""),
            delivery_id=request.headers.get("X-GitHub-Delivery", ""),
            payload=payload if isinstance(payload, dict) else {},
        )
        return Response(out)
