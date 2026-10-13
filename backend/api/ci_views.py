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


def _ci_auth(request, project_id):
    """The authenticated CI token for this project, or None. Tenant validated server-side."""
    from apps.projects.ci_tokens import authenticate_ci_token

    auth = request.headers.get("Authorization", "")
    token = auth[len("CI "):].strip() if auth.startswith("CI ") else ""
    return authenticate_ci_token(
        tenant_id=request.headers.get("X-Tenant-ID"), project_id=str(project_id), token=token)


class CIA11yCandidatesView(APIView):
    """Ingest an accessibility capture from a CI run (QA-11b). CI-token authenticated.

    The same front door as `test-results/`, for the same reason: a client's pipeline can run
    the accessibility suite post-merge, and what it captures should reach the platform the way
    its test results already do.

    **Say this at review rather than letting it be assumed:** the path that will actually run
    today is the companion's — it collects the capture from the build worktree and posts it
    over the runner-token route. Nothing in our CI documentation yet tells a client's pipeline
    to post a capture here, so this endpoint ships correct and, until that documentation
    exists, unexercised by any real caller.

    One screen per post is the rule for both posters: a screen carries a full-page PNG, and a
    body holding ten of them exceeds what the request layer accepts. A document with several
    screens is still read — the bound is the request size, not the format.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, project_id):
        from apps.a11y.capture import CaptureError
        from apps.a11y.ingest import ingest_capture

        ci = _ci_auth(request, project_id)
        if ci is None:
            return Response({"detail": "invalid or missing CI token"},
                            status=status.HTTP_401_UNAUTHORIZED)

        # Raw body, never request.data: the payload is a capture document, and DRF's content
        # negotiation has no business parsing it (same reasoning as the JUnit endpoint).
        try:
            body = request.body.decode("utf-8", "replace") if request.body else ""
        except Exception:  # noqa: BLE001 — an oversized body raises before we can read it
            return Response(
                {"detail": "the capture body was too large to read — post one screen per "
                           "request; a screen carries a full-page screenshot."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        if not body.strip():
            return Response({"detail": "empty request body (expected a capture document)"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            # No run: a CI capture belongs to the project's ongoing regression, not to one of
            # our agent runs, and accepting a caller-supplied run id would let a CI token file
            # candidates against a run it has nothing to do with.
            out = ingest_capture(
                tenant_id=request.headers.get("X-Tenant-ID"), project_id=str(project_id),
                text=body,
            )
        except CaptureError as exc:
            # A readable capture that breaks a bound: nothing was stored, and the reason names
            # what to change. Never a partial store — half a page in a conformance report reads
            # as a page where the other half was fine.
            return Response({"detail": str(exc)},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        code = (status.HTTP_200_OK if out.get("imported")
                else status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(out, status=code)


class CITestResultsView(APIView):
    """Ingest a CI JUnit report → the defect loopback. CI-token authenticated (no session)."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, project_id):
        from apps.quality.ci_ingest import ingest_ci_results

        tenant_id = request.headers.get("X-Tenant-ID")
        ci = _ci_auth(request, project_id)
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
