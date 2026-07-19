"""CI results ingestion endpoint (P3-09bX-3 / spec §2).

`POST /api/projects/<project_id>/test-results/` — the client's CI posts its raw JUnit XML here,
authenticated by a per-project **CI ingest token** (not a session, not a runner enrollment). The
tenant is taken from the `X-Tenant-ID` header and validated against the token server-side, so a
token issued for one project/tenant cannot post to another. Idempotent per CI run via the required
`execution_ref` query param.
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


class CITestResultsView(APIView):
    """Ingest a CI JUnit report → the defect loopback. CI-token authenticated (no session)."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, project_id):
        from apps.projects.ci_tokens import authenticate_ci_token
        from apps.quality.ci_ingest import ingest_ci_results

        tenant_id = request.headers.get("X-Tenant-ID")
        auth = request.headers.get("Authorization", "")
        token = auth[len("CI "):].strip() if auth.startswith("CI ") else ""
        ci = authenticate_ci_token(tenant_id=tenant_id, project_id=str(project_id), token=token)
        if ci is None:
            return Response({"detail": "invalid or missing CI token"},
                            status=status.HTTP_401_UNAUTHORIZED)

        execution_ref = (request.query_params.get("execution_ref") or "").strip()
        if not execution_ref:
            return Response({"detail": "execution_ref query param is required"},
                            status=status.HTTP_400_BAD_REQUEST)

        # Read the raw JUnit body directly (never request.data — the body is XML, not a parsed
        # payload, and we must not trip DRF content-negotiation on it).
        xml_text = request.body.decode("utf-8", "replace") if request.body else ""
        if not xml_text.strip():
            return Response({"detail": "empty request body (expected JUnit XML)"},
                            status=status.HTTP_400_BAD_REQUEST)

        out = ingest_ci_results(
            tenant_id=tenant_id, project_id=str(project_id), xml_text=xml_text,
            execution_ref=execution_ref,
            summary=request.query_params.get("summary", ""),
            commit_sha=request.query_params.get("commit_sha", ""),
            branch=request.query_params.get("branch", ""),
            environment=request.query_params.get("environment", ""),
        )
        # Nothing parseable in the body → 422 so CI sees its report was unusable (wrong file /
        # wrong format), rather than a silent 200. A real report that passed still imports.
        code = status.HTTP_200_OK if out.get("imported") else status.HTTP_422_UNPROCESSABLE_ENTITY
        return Response(out, status=code)
