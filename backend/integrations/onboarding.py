"""Brownfield-lite onboarding (spec §6 / B4) — bring an existing single-repo project
onto the platform two ways, register-don't-recreate:

1. **Static-file extraction:** upload Word/Excel/PDF → store the original in S3 → extract
   to markdown → register a *draft* internal artifact (provenance to the original) →
   **review gate** (`adopt`, product_owner) publishes it. Extraction is lossy/untrusted,
   so adoption is human-gated (#5).
2. **Atlassian register-don't-recreate:** discover existing Confluence pages + Jira issues
   and register *pointers* (never create) — they're already the live SoR, so they're
   indexed as published artifacts / accepted work items. Idempotent by external_ref.

**Full onboarding gap report (Phase 4 §5 / D7):** after discovery has registered what exists
(via the two paths above) and 00c has produced code intelligence, `build_gap_report` does the
**reconcile → gap-detect → report** step the 00 agent reasons over: it assesses each lifecycle
phase Complete / Partial / Missing from the registered artifacts + code-intel + work items,
picks the **resume phase**, and registers a *draft* `gap_report` artifact (published only on the
product_owner gate, #5). Gap-*fill* generation is then the normal phase agents, each gated.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from mcp_platform_state import tools

from .extract import extract, pdf_page_pngs
from .registry import get_capability, get_connection
from .types import CapabilityUnavailable


class OnboardingError(Exception):
    """Onboarding could not proceed (e.g. document not ready for adoption)."""


class OnboardingRoleError(OnboardingError):
    """The adopting user lacks the required role for the review gate."""


def _object_store(injected):
    if injected is not None:
        return injected
    from storage import s3_from_settings

    return s3_from_settings()


# ── static-file extraction ──────────────────────────────────────────
def _supersede_prior_uploads(*, tenant_id, project_id, filename, store) -> None:
    """Replace-on-reupload (BF-BUG-2): delete any existing same-name SourceDocument(s) for this
    project and their extracted artifacts + S3 bodies, so a re-upload leaves exactly one row per
    filename. Runs inside the caller's tenant_context; S3 deletes are best-effort. Artifact
    delete cascades its TraceEdges (registry.TraceEdge FK on_delete=CASCADE)."""
    from apps.integrations.models import SourceDocument
    from apps.registry.models import Artifact

    for prior in SourceDocument.objects.filter(
        tenant_id=tenant_id, project_id=project_id, filename=filename
    ):
        for aid in (prior.extracted_artifact_ids or []):
            art = Artifact.objects.filter(id=aid, tenant_id=tenant_id).first()
            if art is None:
                continue
            if art.s3_key:
                try:
                    store.delete(art.s3_key)
                except Exception:  # noqa: BLE001 — best-effort body cleanup
                    pass
            art.delete()
        if prior.s3_key:
            try:
                store.delete(prior.s3_key)
            except Exception:  # noqa: BLE001 — best-effort source cleanup
                pass
        prior.delete()


def ingest_source_document(*, tenant_id, project_id, filename, mime, content,
                           artifact_type="document", object_store=None) -> dict:
    """Store + extract an uploaded file into a draft internal artifact (provenance kept)."""
    from apps.integrations.models import SourceDocument
    from apps.projects.models import Project
    from apps.tenancy.context import tenant_context
    from storage import content_hash

    store = _object_store(object_store)
    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        # BF-BUG-2: re-uploading a file replaces the prior upload of the same name instead of
        # duplicating it. Supersede any existing same-name source docs + their extracted
        # artifacts (TraceEdge FK is CASCADE, so this is clean) so there is exactly one row per
        # filename. If a prior was already adopted, it is superseded and must be re-adopted.
        _supersede_prior_uploads(tenant_id=tenant_id, project_id=project_id,
                                 filename=filename, store=store)
        src = SourceDocument.objects.create(
            tenant_id=tenant_id, project=project, filename=filename, mime=mime,
            status=SourceDocument.Status.EXTRACTING,
        )
    src_key = f"onboarding/{tenant_id}/{project_id}/{src.id}/source/{filename}"
    store.put(src_key, content)

    try:
        # A1: extract() also returns embedded raster images.
        title, body, images = extract(filename=filename, mime=mime, content=content)
    except Exception:
        with tenant_context(tenant_id):
            SourceDocument.objects.filter(id=src.id, tenant_id=tenant_id).update(
                status=SourceDocument.Status.FAILED, s3_key=src_key
            )
        raise

    # A2: persist the pictorial content so nothing is dropped. For PDFs the faithful visual is a
    # render of each page (it holds tables/diagrams the text can't); for other sources we keep the
    # embedded images. Best-effort — a render failure never fails the upload (text still ingests).
    is_pdf = filename.lower().endswith(".pdf") or (mime or "").lower() == "application/pdf"
    try:
        raw_views = pdf_page_pngs(content) if is_pdf else [im for im in images if im.get("bytes")]
    except Exception:  # noqa: BLE001 — image capture is best-effort
        raw_views = []
    view_keys: list[str] = []
    page_images: list[dict] = []
    for i, im in enumerate(raw_views, start=1):
        name = im.get("name") or f"view{i}.png"
        vkey = f"onboarding/{tenant_id}/{project_id}/{src.id}/views/{name}"
        try:
            store.put(vkey, im["bytes"])
        except Exception:  # noqa: BLE001
            continue
        view_keys.append(vkey)
        page_images.append({"name": name, "s3_key": vkey,
                            "mime": im.get("mime") or "image/png", "page": im.get("page")})

    # A4: derive an honest fidelity marker from what actually came out — text (real body),
    # images_only (no text but page images captured → needs AI read), or empty. Stored in
    # provenance (derived, no DB migration) so the UI badge and gap counting tell the truth.
    if body.strip():
        fidelity = "text"
    elif page_images:
        fidelity = "images_only"
        # BF-BUG-3b: a visual/image-based document. Reassure the user in plain language — the
        # pages ARE preserved and shown below; the AI reads them during onboarding.
        pages = len(page_images)
        body = (
            f"> **Your document is preserved.** `{filename}` is a visual document "
            f"(image-based, with no selectable text). All **{pages} page"
            f"{'s' if pages != 1 else ''}** are saved exactly as you uploaded them — you can "
            "view them from the upload.\n>\n"
            "> During onboarding, the AI reads each screen and diagram into structured text, "
            "so nothing is lost."
        )
    else:
        fidelity = "empty"
        body = (
            f"> **`{filename}` was saved, but no content could be read from it.**\n>\n"
            "> If it should carry content, upload a text-based PDF or DOCX, or link the "
            "original design source."
        )

    body_key = f"onboarding/{tenant_id}/{project_id}/{src.id}/extracted.md"
    store.put(body_key, body)
    # An upload no longer registers an artifact. The registry entry is created ONCE, at adopt —
    # carrying the vision transcription when the pages were read, and the plain extraction when
    # they weren't — so a document the user uploaded once is one artifact at v1, instead of a v1
    # the upload made and a v2 vision replaced it with. Everything the user sees before adopting
    # (title, fidelity badge, page count, previews) comes from the source document, which is why
    # extraction still happens here and the page renders are stored on the document itself.
    #
    # B1-3 still holds: the extracted body + the doc's own state land as one unit, and a failure
    # leaves nothing half-written — the doc is marked FAILED and the staged objects are removed.
    try:
        with tenant_context(tenant_id):
            src = SourceDocument.objects.get(id=src.id, tenant_id=tenant_id)
            src.s3_key = src_key
            src.status = SourceDocument.Status.EXTRACTED
            src.extracted_artifact_ids = []      # filled in at adopt, when the artifact is made
            src.provenance = {"filename": filename, "mime": mime, "source_s3_key": src_key,
                              "title": title, "fidelity": fidelity,
                              "page_count": len(page_images),
                              # The pages must belong to something that exists from upload, and
                              # the artifact no longer does.
                              "page_images": page_images,
                              # The staged extraction: what adopt registers when vision can't
                              # run, and what the content-loss guard measures vision against.
                              "extracted_s3_key": body_key,
                              "extracted_hash": content_hash(body.encode("utf-8")),
                              "artifact_type": artifact_type}
            src.save(update_fields=["s3_key", "status", "extracted_artifact_ids",
                                    "provenance", "updated_at"])
            tools.log_event(tenant_id, "onboarding", "source_document.extracted",
                            "source_document", str(src.id),
                            {"filename": filename, "fidelity": fidelity})
    except Exception:
        with tenant_context(tenant_id):
            SourceDocument.objects.filter(id=src.id, tenant_id=tenant_id).update(
                status=SourceDocument.Status.FAILED, s3_key=src_key)
        for key in [body_key, *view_keys]:
            try:
                store.delete(key)
            except Exception:  # noqa: BLE001
                pass
        raise
    return {"source_document_id": str(src.id), "status": "extracted",
            "artifact_ids": [], "title": title}


def adopt_source_document(*, tenant_id, source_document_id, user_id, target_type=None) -> dict:
    """Review gate: a product_owner publishes the extracted draft artifacts (idempotent).

    Brownfield B2-1 — the human classifies the document here: `target_type` (one of
    ``ADOPTABLE_ARTIFACT_TYPES``) reclassifies the generic extracted ``document`` into its real
    lifecycle type so the gap report recognises it as phase evidence. When omitted, the artifact
    keeps its current type (backward-compatible with pre-B2-1 callers)."""
    from apps.integrations.models import SourceDocument
    from apps.tenancy.context import tenant_context
    from apps.tenancy.models import Membership, User

    if target_type is not None and target_type not in ADOPTABLE_ARTIFACT_TYPES:
        raise OnboardingError(
            f"invalid target_type '{target_type}'; expected one of {ADOPTABLE_ARTIFACT_TYPES}"
        )

    with tenant_context(tenant_id):
        src = SourceDocument.objects.get(id=source_document_id, tenant_id=tenant_id)
        artifact_ids = [str(x) for x in src.extracted_artifact_ids]
        if src.status == SourceDocument.Status.ADOPTED:
            retry_filename = src.filename
            retry_project = str(src.project_id)
            retry_title = (src.provenance or {}).get("title") or src.filename
            return _readopt(
                tenant_id=tenant_id, project_id=retry_project,
                source_document_id=str(src.id), artifact_ids=artifact_ids,
                filename=retry_filename, title=retry_title, user_id=user_id,
                target_type=target_type,
            )
        if src.status != SourceDocument.Status.EXTRACTED:
            raise OnboardingError(f"not ready for adoption (status={src.status})")
        # Adoption is a review gate: the product_owner decides — OR an admin who can approve
        # any gate (project-admin = Membership(role="admin"), or tenant-admin =
        # User.is_tenant_admin), mirroring decide_gate's role check (P4.7-T4).
        has_role = Membership.objects.filter(
            tenant_id=tenant_id, user_id=user_id, project_id=src.project_id,
            role__in=["product_owner", "admin"],
        ).exists()
        if not has_role:
            has_role = User.objects.filter(
                id=user_id, tenant_id=tenant_id, is_tenant_admin=True
            ).exists()
        if not has_role:
            raise OnboardingRoleError(
                f"user {user_id} lacks role 'product_owner' for this project"
            )

    # Documents uploaded before artifacts moved to adopt-time already have their draft artifact:
    # publish and reclassify it as before. Nothing re-registers it, so re-adopting an old document
    # can never mint a duplicate.
    for aid in artifact_ids:
        tools.update_artifact(tenant_id, aid, status="published", type=target_type)
    with tenant_context(tenant_id):
        src = SourceDocument.objects.get(id=source_document_id, tenant_id=tenant_id)
        src.status = SourceDocument.Status.ADOPTED
        src.save(update_fields=["status", "updated_at"])
        filename = src.filename
        project_id = str(src.project_id)
        has_pages = bool((src.provenance or {}).get("page_images")) or bool(artifact_ids)
        doc_title = (src.provenance or {}).get("title") or src.filename
        tools.log_event(tenant_id, f"user:{user_id}", "source_document.adopted",
                        "source_document", str(src.id),
                        {"artifact_ids": artifact_ids, "target_type": target_type})
    # Part B: read the document's visual content into faithful text on the user's machine
    # (document-vision, 00e). For a document uploaded after artifacts moved to adopt time, the
    # vision run is what REGISTERS the artifact — so when vision can't run, adopt must register
    # the plain extraction itself, or the document would be adopted with nothing to show for it.
    # Never fails adoption either way: the document is already adopted by this point.
    vision = _maybe_trigger_vision(
        tenant_id=tenant_id, project_id=project_id, source_document_id=str(source_document_id),
        artifact_ids=artifact_ids, filename=filename, user_id=user_id,
        target_type=target_type, title=doc_title,
    ) if has_pages else _vision_status("no_visuals")
    if not artifact_ids and vision["state"] != "running":
        # No pages to read, no machine connected, or the dispatch failed — the extraction is the
        # document's content, so register it now rather than leave the document empty.
        artifact_ids = [register_extracted_artifact(
            tenant_id=tenant_id, source_document_id=str(source_document_id),
            target_type=target_type,
        )]
    return {"source_document_id": str(source_document_id), "status": "adopted",
            "artifact_ids": artifact_ids, "target_type": target_type, "vision": vision}


def _readopt(*, tenant_id, project_id, source_document_id, artifact_ids, filename, title,
             user_id, target_type) -> dict:
    """Adopt called on a document that is already adopted.

    Adopting twice used to be a plain no-op, which is right when the first adopt worked — but it
    left the user no way back when the reading of a document's pages FAILED. They were told to
    adopt again and nothing happened. So a re-adopt now retries the reading when the last attempt
    failed, and stays a no-op otherwise. The document is adopted either way; only the pass that
    makes its diagrams legible is retried.
    """
    states = vision_states_for_documents(
        tenant_id=tenant_id, project_id=project_id,
        source_document_ids=[str(source_document_id)])
    last = states.get(str(source_document_id))
    # Retry when the last reading FAILED — and equally when one never started at all. The second
    # case is the one the user actually meets: adopting with no machine connected dispatches
    # nothing, so there is no run to have failed, and the message tells them to connect their
    # machine and adopt again. Without this that instruction was a dead end.
    never_ran = last is None and _holds_only_extraction(
        tenant_id=tenant_id, source_document_id=source_document_id)
    if not never_ran and (last is None or last["state"] != "failed"):
        # A reading is running or already done → nothing to retry. `vision: None` = this call
        # started nothing; the key stays present in every adopt response so the UI never has to
        # special-case its absence.
        return {"source_document_id": str(source_document_id), "status": "adopted",
                "artifact_ids": artifact_ids, "idempotent": True, "vision": None}
    # Stand the document back down to "no artifact yet" before retrying, so the retry REGISTERS
    # the document's artifact exactly as the first attempt would have — version 1. Leaving the
    # fallback in place would make the retry supersede it and land on v2, which is the version
    # arithmetic this whole flow exists to avoid. Only the extraction fallback is cleared: a real
    # transcription is never thrown away to make a number look nicer, and if the retry fails too,
    # recovery registers the extraction again.
    cleared = _clear_extraction_fallback(tenant_id=tenant_id, source_document_id=source_document_id)
    vision = _maybe_trigger_vision(
        tenant_id=tenant_id, project_id=project_id, source_document_id=str(source_document_id),
        artifact_ids=[] if cleared else artifact_ids, filename=filename, user_id=user_id,
        target_type=target_type, title=title,
    )
    if cleared and vision["state"] != "running":
        # The retry couldn't start after all — put the extraction back rather than leave the
        # document holding nothing.
        artifact_ids = [register_extracted_artifact(
            tenant_id=tenant_id, source_document_id=str(source_document_id),
            target_type=target_type,
        )]
    elif cleared:
        artifact_ids = []
    return {"source_document_id": str(source_document_id), "status": "adopted",
            "artifact_ids": artifact_ids, "idempotent": True, "retried": True, "vision": vision}


def _holds_only_extraction(*, tenant_id, source_document_id) -> bool:
    """True when the document has pages worth reading but its artifact is still just the plain
    extraction — i.e. a reading is worth (re)starting."""
    from apps.integrations.models import SourceDocument
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        src = SourceDocument.objects.filter(
            id=source_document_id, tenant_id=tenant_id).first()
        if src is None:
            return False
        prov = src.provenance or {}
        if not (prov.get("page_images") or []):
            return False        # nothing visual → a reading would be a no-op
        ids = [str(x) for x in (src.extracted_artifact_ids or [])]
        if not ids:
            return True
        art = Artifact.objects.filter(id=ids[0], tenant_id=tenant_id).first()
        return art is not None and art.s3_key == prov.get("extracted_s3_key")


def _clear_extraction_fallback(*, tenant_id, source_document_id) -> bool:
    """Remove the placeholder artifact a failed reading left behind, so a retry can register the
    document's artifact as version 1.

    Deliberately narrow: it only removes an artifact that IS the staged extraction — same body
    pointer, registered by no run. A transcription (a real vision result, or anything a run
    produced) is never touched, so this can only ever discard a copy of text the platform can
    reproduce from the object store. Returns whether anything was cleared.
    """
    from apps.integrations.models import SourceDocument
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        src = SourceDocument.objects.get(id=source_document_id, tenant_id=tenant_id)
        ids = [str(x) for x in (src.extracted_artifact_ids or [])]
        extracted_key = (src.provenance or {}).get("extracted_s3_key")
        if not ids or not extracted_key:
            return False
        art = Artifact.objects.filter(id=ids[0], tenant_id=tenant_id).first()
        if art is None:
            src.extracted_artifact_ids = []
            src.save(update_fields=["extracted_artifact_ids", "updated_at"])
            return True
        if art.s3_key != extracted_key or art.run_id is not None:
            return False        # a real transcription, not the fallback — leave it alone
        art.delete()
        src.extracted_artifact_ids = []
        src.save(update_fields=["extracted_artifact_ids", "updated_at"])
    return True


def register_extracted_artifact(*, tenant_id, source_document_id, target_type=None) -> str:
    """Register an adopted document's plain extraction as its artifact — version 1, published.

    This is the document's content when its pages were never read: a text-only upload, no machine
    connected, or a vision pass that failed. Because the upload no longer registers anything, this
    is the only thing standing between "adopted" and "the registry has nothing for this document".

    Idempotent by design — if the document already has an artifact (an older upload's draft, or a
    vision pass that got there first), that one stands and its id comes back unchanged. Both this
    and the vision run can reach for the same document, and neither may produce a second artifact.
    """
    from apps.integrations.models import SourceDocument
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        src = SourceDocument.objects.get(id=source_document_id, tenant_id=tenant_id)
        existing = [str(x) for x in (src.extracted_artifact_ids or [])]
        if existing:
            return existing[0]
        prov = src.provenance or {}
        project_id = str(src.project_id)
        filename = src.filename
    artifact = tools.register_artifact(
        tenant_id, project_id, None, phase="onboarding",
        type=target_type or prov.get("artifact_type") or "document",
        sor="internal", content_hash=prov.get("extracted_hash", ""),
        s3_key=prov.get("extracted_s3_key", ""), title=prov.get("title") or filename,
        external_ref={"source": "static_file", "filename": filename,
                      "source_document_id": str(source_document_id),
                      "source_s3_key": prov.get("source_s3_key"),
                      "page_images": prov.get("page_images") or []},
    )
    tools.update_artifact(tenant_id, artifact["id"], status="published")
    with tenant_context(tenant_id):
        SourceDocument.objects.filter(id=source_document_id, tenant_id=tenant_id).update(
            extracted_artifact_ids=[artifact["id"]])
    return str(artifact["id"])


#: What the user is told about the vision pass after adopting (Part B fix 3). Adoption itself
#: always succeeds — vision only enriches the extracted text — but "succeeded silently" and
#: "never ran at all" looked identical to the user, and the most common cause (no companion) is
#: one the user can fix in a click. Each state carries a finished sentence rather than a code the
#: UI has to translate, so no screen ever shows a raw identifier.
VISION_STATES = {
    "running": "Reading the diagrams and screenshots in this document. The text will update on "
               "its own when it finishes.",
    "no_visuals": "No diagrams or images were found in this document, so there was nothing "
                  "further to read.",
    "already_running": "This document's diagrams are already being read.",
    "failed": "The diagrams in this document could not be read. The adopted text is unaffected.",
}


def _vision_status(state, message=None, run_id=None) -> dict:
    return {"state": state, "message": message or VISION_STATES[state],
            "run_id": str(run_id) if run_id else None}


#: What a *dispatched* vision run's state means to the user (Part B fix 4). The adopt response
#: only reports the moment of dispatch; a run that starts and then dies afterwards would leave the
#: user watching "Reading the diagrams…" forever, because the carrier work item is deliberately
#: hidden from the backlog and nothing else points at it. These states are read back from the run
#: itself so the document row can tell the truth on every later page load, not just at adopt.
_VISION_RUN_STATES = {
    "pending": ("running", VISION_STATES["running"]),
    "running": ("running", VISION_STATES["running"]),
    "completed": ("done", "The diagrams and screenshots in this document have been read into "
                          "text."),
    "approved": ("done", "The diagrams and screenshots in this document have been read into "
                         "text."),
    "failed": ("failed", "Reading this document's diagrams didn't finish, so it holds the plain "
                         "extracted text for now. Adopt it again to retry."),
    "rejected": ("failed", "Reading this document's diagrams didn't finish, so it holds the plain "
                           "extracted text for now. Adopt it again to retry."),
    "stalled": ("failed", "Reading this document's diagrams stopped without finishing — your "
                          "machine didn't report back. It holds the plain extracted text for "
                          "now. Adopt it again to retry."),
}


def vision_states_for_documents(*, tenant_id, project_id, source_document_ids) -> dict:
    """Latest vision-run state per source document, for the document list (Part B fix 4).

    Resolved in two bulk queries — the carriers for this project, then their newest runs — so a
    20-document list costs the same as a 1-document list. Documents with no vision run simply
    aren't in the returned map; the UI shows nothing for them, which is correct (there was
    nothing to read, or the pass never started and adopt already said so).
    """
    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    wanted = {str(i) for i in source_document_ids}
    if not wanted:
        return {}
    with tenant_context(tenant_id):
        carriers = {
            str(wi.external_ref.get("source_document_id")): wi.id
            for wi in WorkItem.objects.filter(
                tenant_id=tenant_id, project_id=project_id,
                external_ref__source="vision_carrier",
            )
            if str((wi.external_ref or {}).get("source_document_id")) in wanted
        }
        if not carriers:
            return {}
        newest = {}
        for run in (
            Run.objects.filter(tenant_id=tenant_id, work_item_id__in=list(carriers.values()))
            .order_by("work_item_id", "-created_at")
        ):
            newest.setdefault(str(run.work_item_id), run)
    out = {}
    for doc_id, wi_id in carriers.items():
        run = newest.get(str(wi_id))
        if run is None:
            continue
        mapped = _VISION_RUN_STATES.get(run.status)
        if mapped is None:
            continue        # awaiting_gate can't occur here (auto-apply opens no gate)
        state, message = mapped
        out[doc_id] = {"state": state, "message": message, "run_id": str(run.id)}
    return out


def _maybe_trigger_vision(*, tenant_id, project_id, source_document_id, artifact_ids, filename,
                          user_id, target_type=None, title=None) -> dict:
    """Kick off the document-vision agent (00e) for an adopted document, and report what happened.

    Only runs when there is something visual to read (the artifact has preserved `page_images`); a
    pure-text upload would give vision nothing to do. Still fully best-effort — no enrolled
    companion, an already-running pass for this document, or any other error never fails adoption,
    which has already succeeded by the time we get here.

    What changed in Part B fix 3: these outcomes used to be swallowed. `NoCompanionError` even
    carries a written, user-ready explanation, which was caught and discarded — so a user with no
    companion running got none of the benefit, no message, and no way to know. Every outcome now
    comes back as a state + a plain sentence the adopt response hands to the UI.
    """
    pages, _found = tools.page_images_for(tenant_id, str(source_document_id))
    if not pages:
        return _vision_status("no_visuals")  # nothing visual to read → vision would be a no-op
    # The run is pointed at the SOURCE DOCUMENT, not an artifact: for a document uploaded after
    # artifacts moved to adopt time there is no artifact yet — this run is what creates it.
    # `get_page_images` takes either id, so an older document still resolves through its artifact.
    artifact_id = str(artifact_ids[0]) if artifact_ids else str(source_document_id)
    try:
        from orchestration.trigger import ActiveRunError, NoCompanionError, trigger_vision

        result = trigger_vision(
            tenant_id=tenant_id, project_id=project_id, source_document_id=source_document_id,
            artifact_id=artifact_id, filename=filename, triggered_by=user_id,
            target_type=target_type, title=title,
        )
    except NoCompanionError as exc:
        # The message is written for a human and tells them exactly what to do — show it.
        return _vision_status("no_companion", str(exc))
    except ActiveRunError:
        return _vision_status("already_running")
    except Exception as exc:  # noqa: BLE001 — vision is an enhancement; never fail adoption
        tools.log_event(tenant_id, "platform", "document_vision.trigger_failed",
                        "source_document", source_document_id, {"error": str(exc)[:300]})
        return _vision_status("failed")
    return _vision_status("running", run_id=getattr(result, "run_id", None))


# ── Atlassian register-don't-recreate ───────────────────────────────
_ISSUE_TYPE = {"Epic": "epic", "Story": "story", "Task": "task",
               "Sub-task": "task", "Subtask": "task"}


def register_atlassian(*, tenant_id, project_id, tasktracker=None, project_key=None) -> dict:
    """Import an existing **Jira backlog** as work-item pointers, creating nothing in Jira (B1).

    Brownfield redesign (B3-1/B3-4): this no longer crawls the whole Confluence space. A backlog
    is meant to arrive whole, so Jira stays a bulk import; but a Confluence space of hundreds of
    pages can't be auto-typed, and crawling it registered every page as an untyped `document`
    that the gap report ignores. Confluence docs are now linked individually + typed via
    `link_confluence_pages` (B3-4). Graceful (B3-1): if Jira isn't connected this **skips**
    (no error) and reports it — mirroring the publish path — so onboarding never hits a dead-end
    400; the hub drives the "connect Jira" affordance from the connection status instead."""
    from apps.projects.models import Project
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    if tasktracker is None:
        try:
            tasktracker = get_capability(tenant_id, "tasktracker")
        except CapabilityUnavailable:
            return {"registered_issues": [], "tasktracker_connected": False}
    if project_key is None:
        conn = get_connection(tenant_id, "tasktracker")
        project_key = (conn.scopes or {}).get("project_key") if conn else None

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        existing_issues = {
            (w.external_ref or {}).get("id")
            for w in WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id)
            if w.external_ref
        }

    registered_issues: list[str] = []
    for hit in (tasktracker.search(jql=f'project = "{project_key}"') if project_key else []):
        if hit.key in existing_issues:
            continue
        issue = tasktracker.get_issue(issue_ref=hit.key)
        with tenant_context(tenant_id):
            project = Project.objects.get(id=project_id, tenant_id=tenant_id)
            wi = WorkItem.objects.create(
                tenant_id=tenant_id, project=project,
                type=_ISSUE_TYPE.get(issue.issue_type, "task"), title=issue.summary,
                state=WorkItem.State.ACCEPTED,
                external_ref={"sor": "jira", "id": issue.key, "url": issue.url},
            )
            tools.log_event(tenant_id, "onboarding", "issue.registered", "work_item",
                            str(wi.id), {"issue": issue.key})
        registered_issues.append(hit.key)

    return {"registered_issues": registered_issues, "tasktracker_connected": True}


def _parse_confluence_page_id(raw: str) -> str | None:
    """Extract a Confluence page id from a pasted link or a bare id (B3-4). Handles Cloud
    (`/wiki/spaces/<SPACE>/pages/<id>/<slug>` or `.../pages/<id>`) and Server/DC
    (`viewpage.action?pageId=<id>`); a bare numeric id passes through. Returns `None` if no id
    can be found — the caller then shows a "paste the full URL or the page ID" error. "Tiny"
    share links (`/x/<code>`) can't be resolved offline, so those fall back to that message."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    # Server/DC: ...viewpage.action?pageId=12345
    page_id_qs = parse_qs(parsed.query or "").get("pageId", [])
    if page_id_qs and page_id_qs[0].isdigit():
        return page_id_qs[0]
    # Cloud: .../pages/<id>/<slug> — the numeric segment immediately after "pages".
    segments = [s for s in (parsed.path or "").split("/") if s]
    for i, seg in enumerate(segments):
        if seg == "pages" and i + 1 < len(segments) and segments[i + 1].isdigit():
            return segments[i + 1]
    return None


def link_confluence_pages(*, tenant_id, project_id, links, docstore=None) -> dict:
    """B3-4 — register user-provided Confluence pages as **typed** pointers so the gap report
    sees them as phase evidence. Each `links` row = `{"page": <url-or-id>, "type": <canonical
    lifecycle type>}`. Register-don't-recreate: stores a pointer (id/url/title), never the page
    body; idempotent by page id (re-linking updates the declared type, never duplicates). Shares
    the canonical type set (`ADOPTABLE_ARTIFACT_TYPES`) + the typed-registration path with
    uploaded-doc adoption (B2-1) — one classification path, two sources. Per-row errors are
    collected, not raised, so one bad link doesn't fail the whole batch."""
    from apps.projects.models import Project
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    if docstore is None:
        # No docstore connector → CapabilityUnavailable, mapped to a friendly 4xx at the view.
        docstore = get_capability(tenant_id, "docstore")

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        existing = {
            (a.external_ref or {}).get("id"): a
            for a in Artifact.objects.filter(
                tenant_id=tenant_id, project_id=project_id, sor="confluence")
        }

    linked: list[dict] = []
    errors: list[dict] = []
    for row in links:
        raw = (row or {}).get("page", "")
        target_type = (row or {}).get("type", "")
        if target_type not in ADOPTABLE_ARTIFACT_TYPES:
            errors.append({"page": raw, "error": f"unknown type {target_type!r}"})
            continue
        page_id = _parse_confluence_page_id(raw)
        if not page_id:
            errors.append({"page": raw,
                           "error": "couldn't find that page — paste the full URL or the page ID"})
            continue
        try:
            page = docstore.get_page(page_ref=page_id)
        except Exception:  # noqa: BLE001 — per-row error; don't fail the batch
            errors.append({"page": raw, "error": "couldn't read that page from Confluence"})
            continue
        existing_art = existing.get(page_id)
        if existing_art is not None:
            # Idempotent: update the declared type on the existing pointer, never duplicate.
            tools.update_artifact(tenant_id, str(existing_art.id),
                                  status="published", type=target_type)
            linked.append({"page_id": page_id, "artifact_id": str(existing_art.id),
                           "type": target_type, "title": page.title, "created": False})
            continue
        art = tools.register_artifact(
            tenant_id, project_id, None, phase="onboarding", type=target_type,
            sor="confluence", content_hash="",
            external_ref={"sor": "confluence", "id": page_id, "url": page.url,
                          "title": page.title},
        )
        tools.update_artifact(tenant_id, art["id"], status="published")
        linked.append({"page_id": page_id, "artifact_id": art["id"], "type": target_type,
                       "title": page.title, "created": True})

    return {"linked": linked, "errors": errors}


# ── full onboarding: reconcile → gap report → resume (D7) ────────────
# The lifecycle, in order, with the registered artifact types that evidence each phase.
# Resume = the first phase that is not Complete; the report names what is missing before it.
_LIFECYCLE: list[tuple[str, str, tuple[str, ...]]] = [
    ("ideation", "1. Ideation", ("ideation",)),
    ("requirements", "2. Requirements", ("requirements",)),
    ("prd", "3. PRD", ("prd",)),
    ("architecture", "4. Architecture",
     ("architecture", "adr", "data_model", "api_spec", "tech_stack", "security_architecture")),
    ("ux_design", "5. UX Design",
     ("ux_design", "user_journey", "wireframe", "design_system", "accessibility")),
    ("task_breakdown", "6. Task Breakdown", ("task_breakdown",)),
    ("implementation", "7. Implementation", ("code",)),
    ("code_review", "8. Code Review", ("code_review",)),
    ("testing", "9. Testing & QA", ("test_case", "test_report")),
    ("security", "10. Security",
     ("security_review", "security_finding", "threat_model", "sbom")),
    ("cicd", "11. CI/CD", ("cicd", "pipeline")),
    ("deployment", "12. Deployment", ("deployment", "release")),
]
_BACKLOG_TYPES = ("epic", "story", "task")

# Brownfield: a client can hold ANY phase's evidence as a document — test cases in a
# spreadsheet, a code review in a Word doc, a threat model as a PDF — so adoption spans the
# FULL lifecycle vocabulary. The ONE exclusion is the implementation phase (`code`): a running
# codebase is evidenced from git via code intelligence, never an uploaded file. Derived from
# _LIFECYCLE so the adopt vocabulary can never drift from what the gap-report assessor reads.
_NON_ADOPTABLE_PHASES = ("implementation",)
ADOPTABLE_ARTIFACT_TYPES = tuple(
    t
    for phase, _label, types in _LIFECYCLE
    if phase not in _NON_ADOPTABLE_PHASES
    for t in types
)

# Human-readable labels per artifact type (falls back to Title-Case of the slug). Kept beside
# the vocabulary it labels so a new _LIFECYCLE type is a one-line addition.
_TYPE_LABELS = {
    "ideation": "Ideation", "requirements": "Requirements", "prd": "PRD",
    "architecture": "Architecture", "adr": "ADR", "data_model": "Data Model",
    "api_spec": "API Spec", "tech_stack": "Tech Stack",
    "security_architecture": "Security Architecture", "ux_design": "UX Design",
    "user_journey": "User Journey", "wireframe": "Wireframe",
    "design_system": "Design System", "accessibility": "Accessibility",
    "task_breakdown": "Task Breakdown", "code_review": "Code Review",
    "test_case": "Test Case", "test_report": "Test Report",
    "security_review": "Security Review", "security_finding": "Security Finding",
    "threat_model": "Threat Model", "sbom": "SBOM", "cicd": "CI/CD",
    "pipeline": "Pipeline", "deployment": "Deployment", "release": "Release",
}


def _humanize_type(value: str) -> str:
    return _TYPE_LABELS.get(value) or value.replace("_", " ").title()


def adoptable_type_choices() -> list[dict]:
    """The adopt/link dropdown vocabulary, served so the frontend never drifts from the backend.
    One entry per adoptable type, labelled '<Type> (<Phase>)' so each option is self-describing.
    Single source of truth = _LIFECYCLE (minus the git-only implementation phase)."""
    choices: list[dict] = []
    for phase, label, types in _LIFECYCLE:
        if phase in _NON_ADOPTABLE_PHASES:
            continue
        phase_label = label.split(". ", 1)[-1]  # "5. UX Design" -> "UX Design"
        for t in types:
            choices.append({
                "value": t,
                "type_label": _humanize_type(t),
                "phase": phase,
                "phase_label": phase_label,
                "label": f"{_humanize_type(t)} ({phase_label})",
            })
    return choices


def ensure_onboarding_work_item(*, tenant_id, project_id, repo_id=None):
    """Get-or-create the per-project carrier work item the onboarding AGENTS run against.

    Onboarding is project-scoped, but the agent machinery (`trigger_phase` → `AgentRunWorkflow`
    → gate → verify_writes) is per-WorkItem. So the platform holds ONE carrier `epic` per
    onboarding target: a repo-agnostic carrier for the whole-project assessment (00_onboarding),
    and one carrier pinned to each repo for its code intelligence (00c) — the pin is what lets a
    multi-repo project index the right repo without tripping the planner-ambiguity guard.
    Idempotent by (project, marker, repo)."""
    from apps.projects.models import Project, Repository
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    repo_key = str(repo_id) if repo_id else None
    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        existing = WorkItem.objects.filter(
            tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.EPIC,
            external_ref__source="onboarding_carrier", external_ref__repo_id=repo_key,
        ).first()
        if existing is not None:
            return existing
        repo = None
        title = "Onboarding — project assessment"
        if repo_key:
            repo = Repository.objects.filter(
                id=repo_id, tenant_id=tenant_id, project_id=project_id).first()
            title = f"Onboarding — code intelligence ({repo.name if repo else repo_key})"
        return WorkItem.objects.create(
            tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.EPIC,
            state=WorkItem.State.ACCEPTED, title=title, repo=repo,
            external_ref={"source": "onboarding_carrier", "repo_id": repo_key},
        )


# Work-item `external_ref.source` markers that identify a CARRIER — an internal plumbing work
# item that only exists to host an onboarding/vision agent run, never a backlog item a human
# authored. The user-facing work-item list hides these (api WorkItemViewSet) so they never clutter
# the backlog; the trigger/run machinery still resolves them by their external_ref markers.
CARRIER_SOURCES = ("onboarding_carrier", "vision_carrier")


def ensure_vision_work_item(*, tenant_id, project_id, source_document_id, artifact_id, filename,
                            target_type=None, title=None):
    """Get-or-create the per-DOCUMENT carrier work item a document-vision (00e) run executes
    against — one per adopted document, so concurrent adopts never collide on a shared carrier and
    the run's completion `done`-transition is harmless. Hidden from the backlog (CARRIER_SOURCES).
    The description names the target artifact so the agent reads it straight from its manifest.
    Idempotent by (project, source, source_document_id)."""
    from apps.projects.models import Project
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        existing = WorkItem.objects.filter(
            tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.EPIC,
            external_ref__source="vision_carrier",
            external_ref__source_document_id=str(source_document_id),
        ).first()
        # Two shapes, because a document uploaded before artifacts moved to adopt time already
        # HAS an artifact to version, while a new one does not exist in the registry until this
        # run creates it. The description is the agent's only instruction about which it is.
        if str(artifact_id) != str(source_document_id):
            description = (
                "Transcribe the adopted document into faithful text. Target document artifact: "
                f"{artifact_id} (file: {filename}). Read its pages with get_page_images, then "
                "re-register it as a new version carrying your faithful transcription, passing "
                f"supersedes={artifact_id} so it versions this document instead of duplicating it."
            )
        else:
            description = (
                "Transcribe the adopted document into faithful text — this run REGISTERS the "
                f"document's artifact, so it does not exist yet. Source document: {artifact_id} "
                f"(file: {filename}). Read its pages with get_page_images using that id, read the "
                "already-extracted text with get_source_extraction, then register ONE artifact "
                f"with phase=\"onboarding\", type=\"{target_type or 'document'}\", "
                f"title=\"{title or filename}\" carrying the extracted text AND everything the "
                "pages hold. Do not pass supersedes — there is nothing to supersede."
            )
        if existing is not None:
            # Keep the pointer fresh if the doc was re-adopted (the artifact id can change).
            existing.description = description
            existing.external_ref = {"source": "vision_carrier",
                                     "source_document_id": str(source_document_id),
                                     "artifact_id": str(artifact_id), "filename": filename}
            existing.save(update_fields=["description", "external_ref", "updated_at"])
            return existing
        return WorkItem.objects.create(
            tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.EPIC,
            state=WorkItem.State.ACCEPTED, title=f"Document vision — {filename}",
            description=description,
            external_ref={"source": "vision_carrier",
                          "source_document_id": str(source_document_id),
                          "artifact_id": str(artifact_id), "filename": filename},
        )


def _assess_phase(phase, types, by_type, *, has_backlog, intel_present):
    """Complete / Partial / Missing for one lifecycle phase, with its evidence artifacts.

    Published artifacts (or strong non-artifact evidence) → Complete; only drafts → Partial
    (registered, not yet adopted); nothing → Missing. Two phases carry non-document evidence
    the legacy agent assesses rather than generates: Task Breakdown from the accepted backlog,
    Implementation from the code itself (code intelligence proves the codebase exists)."""
    evidence = [a for t in types for a in by_type.get(t, [])]
    published = [a for a in evidence if a.status == "published"]
    strong = (phase == "task_breakdown" and has_backlog) or \
             (phase == "implementation" and intel_present)
    weak = (phase == "implementation" and intel_present)  # code exists but unverified vs docs
    if published or strong:
        status = "complete"
    elif evidence or weak:
        status = "partial"
    else:
        status = "missing"
    return status, evidence


def write_gap_report_artifact(
    *, tenant_id, project_id, phases, resume, blockers, intel_present,
    evidence_ids=(), object_store=None,
) -> dict:
    """Render + persist the canonical draft `gap_report` artifact and return the REST-shaped
    result. This is the ONE writer of the `external_ref` shape that `read_gap_report` + the whole
    UI depend on — shared by the deterministic `build_gap_report` AND the agent path's
    `submit_gap_report` tool, so neither can emit a shape the reader can't parse.

    `phases` is the canonical list [{phase, label, status, evidence:[...]}]; `evidence_ids` are
    the artifact ids the report derives from (trace edges)."""
    from storage import content_hash

    store = _object_store(object_store)
    # _render_gap_report shows an evidence count per phase; fill it from the evidence list so the
    # agent path (which may omit it) renders identically to the deterministic path.
    render_phases = [
        {**p, "evidence_count": p.get("evidence_count", len(p.get("evidence") or []))}
        for p in phases
    ]
    resume_label = next(
        (p["label"] for p in phases if p["phase"] == resume), "Pipeline complete")
    body = _render_gap_report(render_phases, resume_label, blockers, intel_present)
    body_key = f"onboarding/{tenant_id}/{project_id}/gap_report.md"
    store.put(body_key, body)
    report = tools.register_artifact(
        tenant_id, project_id, None, phase="onboarding", type="gap_report",
        sor="internal", content_hash=content_hash(body.encode("utf-8")), s3_key=body_key,
        external_ref={"source": "onboarding", "resume_phase": resume,
                      "phases": [{"phase": p["phase"], "label": p["label"], "status": p["status"],
                                 "evidence": p.get("evidence", [])} for p in phases],
                      "blockers": blockers, "intel_present": intel_present},
    )
    for aid in list(dict.fromkeys(evidence_ids))[:200]:
        tools.add_trace_edge(tenant_id, report["id"], aid, "derives")
    tools.log_event(tenant_id, "onboarding", "gap_report.built", "artifact", report["id"],
                    {"resume_phase": resume, "blockers": blockers})
    return {"gap_report_id": report["id"], "resume_phase": resume, "phases": phases,
            "blockers": blockers, "intel_present": intel_present}


def build_gap_report(*, tenant_id, project_id, object_store=None) -> dict:
    """Reconcile what onboarding discovered into a **gap report** (D7) and pick the resume
    phase — the DETERMINISTIC fallback for when no companion is enrolled (the agent path,
    `00_onboarding` → `submit_gap_report`, is primary). Assesses every lifecycle phase from the
    registered artifacts + code-intel + work items, then writes the same canonical draft
    `gap_report` via `write_gap_report_artifact`. Builds on `register_atlassian` /
    `ingest_source_document` / 00c — it never re-creates content, only reports on it."""
    from apps.projects.models import Project
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        artifacts = list(
            Artifact.objects.filter(tenant_id=tenant_id, project_id=project_id)
            .exclude(type="gap_report")  # don't assess prior reports as evidence
        )
        work_items = list(WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id))

    by_type: dict[str, list] = {}
    for a in artifacts:
        by_type.setdefault(a.type, []).append(a)
    has_backlog = any(w.type in _BACKLOG_TYPES for w in work_items)
    intel_present = bool(by_type.get("codebase_intelligence"))

    phases: list[dict] = []
    evidence_ids: list[str] = []
    for phase, label, types in _LIFECYCLE:
        status, evidence = _assess_phase(
            phase, types, by_type, has_backlog=has_backlog, intel_present=intel_present)
        # Light refs (id/type/sor/status), capped — enough for the REST read-through (T8) to
        # render "Evidence" without re-querying; never the artifact body.
        refs = [{"artifact_id": str(a.id), "type": a.type, "sor": a.sor, "status": a.status}
                for a in evidence[:10]]
        phases.append({"phase": phase, "label": label, "status": status,
                       "evidence_count": len(evidence), "evidence": refs})
        evidence_ids.extend(str(a.id) for a in evidence)

    resume = next((p["phase"] for p in phases if p["status"] != "complete"), "done")
    # Blockers: phases still Missing at or before the resume point — they gate forward progress.
    resume_idx = next((i for i, p in enumerate(phases) if p["phase"] == resume), len(phases))
    blockers = [p["phase"] for p in phases[: resume_idx + 1] if p["status"] == "missing"]

    return write_gap_report_artifact(
        tenant_id=tenant_id, project_id=project_id, phases=phases, resume=resume,
        blockers=blockers, intel_present=intel_present, evidence_ids=evidence_ids,
        object_store=object_store,
    )


def _render_gap_report(phases, resume_label, blockers, intel_present) -> str:
    icon = {"complete": "Complete", "partial": "Partial", "missing": "Missing"}
    lines = [
        "# Onboarding Gap Report",
        "",
        "> Generated by the Onboarding Agent — what existed, what was registered, "
        "and what is still missing before the pipeline resumes.",
        "",
        f"**Code intelligence:** {'available' if intel_present else 'not run'}",
        f"**Recommended resume phase:** {resume_label}",
        "",
        "## Phase Completion Assessment",
        "",
        "| Phase | Status | Evidence |",
        "|-------|--------|----------|",
    ]
    lines += [f"| {p['label']} | {icon[p['status']]} | {p['evidence_count']} artifact(s) |"
              for p in phases]
    lines += ["", "## Blockers (resolve before resuming)", ""]
    lines += ([f"- **{b}** — no evidence found; generate via its phase agent (gated) "
               "or provide the source." for b in blockers] or ["- None."])
    return "\n".join(lines) + "\n"


# ── REST layer (P4.7-T8, backs S-24/S-25/S-26) ───────────────────────
def read_gap_report(*, tenant_id, project_id) -> dict | None:
    """Read-through the latest registered `gap_report` (S-26) — no recompute; `None` when
    none has been built yet. `POST .../gap-report/` (`build_gap_report`) is what (re)builds
    it; re-running after new evidence is registered is how the resume point moves."""
    from apps.projects.models import Project
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        report = (
            Artifact.objects.filter(tenant_id=tenant_id, project_id=project_id, type="gap_report")
            .order_by("-created_at").first()
        )
    if report is None:
        return None
    ext = report.external_ref or {}
    return {
        "gap_report_id": str(report.id),
        "resume_phase": ext.get("resume_phase"),
        "intel_present": ext.get("intel_present", False),
        "phases": [
            # assessment values are lowercase to match the frontend GapPhaseAssessment type:
            # "complete" | "partial" | "missing"  (never capitalised in the REST response)
            {"phase": p["phase"], "assessment": p["status"],
             "evidence": p.get("evidence", [])}
            for p in ext.get("phases", [])
        ],
        "blocking": ext.get("blockers", []),
    }


def submit_agent_gap_report(
    *, tenant_id, project_id, phases, resume_phase=None, blockers=None, object_store=None,
) -> dict:
    """Normalize an AGENT's phase assessment (00_onboarding) into the canonical draft
    `gap_report`. The agent supplies reasoned per-phase statuses (+ optional evidence refs); this
    coerces to the exact `_LIFECYCLE` shape `read_gap_report` expects — filling any omitted phase
    as 'missing', validating statuses, and deriving `resume`/`blockers` when the agent's are
    unusable — then writes via the shared writer, so the REST/UI contract is guaranteed no matter
    what the model emitted."""
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    valid = {"complete", "partial", "missing"}
    supplied: dict[str, dict] = {}
    for p in (phases or []):
        if isinstance(p, dict) and p.get("phase") and p.get("status") in valid:
            ev = p.get("evidence")
            supplied[p["phase"]] = {
                "status": p["status"], "evidence": ev if isinstance(ev, list) else [],
            }
    canonical = []
    for phase, label, _types in _LIFECYCLE:
        s = supplied.get(phase, {"status": "missing", "evidence": []})
        canonical.append({"phase": phase, "label": label, "status": s["status"],
                          "evidence": s["evidence"]})

    known = {p["phase"] for p in canonical}
    derived_resume = next((p["phase"] for p in canonical if p["status"] != "complete"), "done")
    resume = resume_phase if resume_phase in known else derived_resume
    if isinstance(blockers, list) and blockers:
        blockers = [b for b in blockers if b in known]
    else:
        idx = next((i for i, p in enumerate(canonical) if p["phase"] == resume), len(canonical))
        blockers = [p["phase"] for p in canonical[: idx + 1] if p["status"] == "missing"]

    with tenant_context(tenant_id):
        intel_present = Artifact.objects.filter(
            tenant_id=tenant_id, project_id=project_id, type="codebase_intelligence"
        ).exists()

    evidence_ids = [
        e.get("artifact_id") for p in canonical for e in p["evidence"]
        if isinstance(e, dict) and e.get("artifact_id")
    ]
    return write_gap_report_artifact(
        tenant_id=tenant_id, project_id=project_id, phases=canonical, resume=resume,
        blockers=blockers, intel_present=intel_present, evidence_ids=evidence_ids,
        object_store=object_store,
    )


def record_code_intel_index(*, tenant_id, project_id, repo_id, index=None, summary="",
                            object_store=None) -> dict:
    """Persist a code-intel analysis as a `codebase_intelligence` artifact + Knowledge-Index
    chunk (S-24 step 3). The built-in analyzer runs in the companion worktree (D2); this call
    persists an **already-computed** result — it never touches the source (#1/#3). Real
    companion-side dispatch (claim → analyze → report) is deferred; see PHASE_4.7_BUILD_SPEC.md
    T8 implementation notes."""
    from apps.knowledge.index import index_artifact
    from apps.projects.models import Project, Repository
    from apps.tenancy.context import tenant_context
    from storage import content_hash

    index = index or {}
    store = _object_store(object_store)
    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        repo = Repository.objects.get(id=repo_id, tenant_id=tenant_id, project_id=project_id)

    text = summary.strip() if summary else f"Code intelligence index for {repo.name}."
    body = _render_code_intel_summary(repo.name, index, text)
    body_key = f"onboarding/{tenant_id}/{project_id}/code_intel/{repo.id}.md"
    store.put(body_key, body)
    # Keep the registry POINTER lean — scalar summary only; the rich detail (hotspot files, dead
    # code, decisions) lives in the body in S3, never bloating the external_ref (#3).
    ref_summary = {k: index[k] for k in ("file_count", "commits", "hotspots", "authors",
                                         "communities", "languages") if k in index}
    artifact = tools.register_artifact(
        tenant_id, project_id, None, phase="context_extraction", type="codebase_intelligence",
        sor="internal", content_hash=content_hash(body.encode("utf-8")), s3_key=body_key,
        external_ref={"source": "code_intel", "repo": repo.name, **ref_summary},
        repo_id=str(repo.id),
    )
    # Index the rich rendered body (not just the one-line summary) so the hotspot files, dead
    # code and decisions are retrievable knowledge for downstream agents.
    index_artifact(tenant_id=tenant_id, project_id=project_id, artifact_id=artifact["id"],
                   text=body, repo_id=str(repo.id), source="code_intel")
    tools.log_event(tenant_id, "onboarding", "code_intel.indexed", "artifact", artifact["id"],
                    {"repo_id": str(repo.id), "file_count": index.get("file_count")})
    return {"artifact_id": artifact["id"], "repo_id": str(repo.id), "status": "indexed"}


_LANG_NAMES = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript (React)", ".js": "JavaScript",
    ".jsx": "JavaScript (React)", ".go": "Go", ".java": "Java", ".rb": "Ruby",
    ".rs": "Rust", ".kt": "Kotlin",
}


def _fmt_languages(languages: dict) -> str:
    """A readable language breakdown from the analyzer's `{'.py': 4}` extension counts."""
    if not languages:
        return "—"
    return ", ".join(f"{_LANG_NAMES.get(ext, ext)} ({cnt})"
                     for ext, cnt in sorted(languages.items(), key=lambda kv: -kv[1]))


def _dead_name(entry) -> str:
    if isinstance(entry, dict):
        return entry.get("file") or entry.get("path") or next(iter(entry.values()), "?")
    return str(entry)


def _render_code_intel_summary(repo_name: str, index: dict, summary: str) -> str:
    """Render the code-intelligence index into a human-readable report that shows the analyzer's
    real depth — the five intelligence layers (git activity · architecture/dependency graph · risk
    hotspots · dead code · decision archaeology) — not just counts. Degrades gracefully to a basic
    summary when only counts were reported (older/thin payloads)."""
    g = index.get
    lines = [
        f"# Code Intelligence — {repo_name}", "",
        summary or ("Static analysis of the existing codebase — computed on your companion in a "
                    "read-only worktree; only this index is stored, never your source."),
        "",
        "## Overview", "",
        f"- **Files analysed:** {g('file_count', '—')}",
        (f"- **Commits:** {g('commits', '—')}"
         + (f" · **Authors:** {g('authors')}" if g("authors") is not None else "")),
        f"- **Languages:** {_fmt_languages(g('languages') or {})}",
    ]
    entry_points = g("entry_points") or []
    if entry_points:
        shown = ", ".join(f"`{e}`" for e in entry_points[:8])
        lines.append(f"- **Entry points:** {shown}" + (" …" if len(entry_points) > 8 else ""))

    # Architecture — dependency communities + the most-depended-on modules (PageRank).
    communities, top_modules = g("communities"), g("top_modules") or []
    if communities is not None or top_modules:
        lines += ["", "## Architecture", ""]
        if communities is not None:
            lines.append(f"- **Cohesive modules (dependency communities):** {communities}")
        if top_modules:
            lines.append("- **Most-depended-on files (PageRank):**")
            lines += [f"  - `{m}`" for m in top_modules[:8]]

    # Risk hotspots — churn × complexity (Tornhill), the highest-signal quality indicator.
    hotspots = g("hotspot_files") or []
    if hotspots:
        lines += ["", "## Risk hotspots (churn × complexity)", "",
                  "| File | Score | Churn | Complexity |", "|------|------:|------:|-----------:|"]
        lines += [f"| `{h.get('file', '?')}` | {h.get('score', '—')} | "
                  f"{h.get('churn', '—')} | {h.get('complexity', '—')} |" for h in hotspots[:10]]

    # Dead code — files nothing imports (excluding entry points).
    dead = g("dead_code") or []
    if dead:
        names = [_dead_name(d) for d in dead]
        lines += ["", f"## Likely dead code ({len(names)})", ""]
        lines += [f"- `{n}`" for n in names[:15]]
        if len(names) > 15:
            lines.append(f"- …and {len(names) - 15} more")

    # Decision archaeology — ADRs + notable commit messages.
    decisions = g("decisions") or []
    if decisions:
        lines += ["", f"## Decisions found ({len(decisions)})", ""]
        for d in decisions[:10]:
            title = d.get("title") or d.get("ref") or "decision"
            ref = d.get("ref", "")
            lines.append(f"- {title}" + (f" ({ref})" if ref and ref != title else ""))

    # Thin/older payload (counts only) — surface the hotspot count so the body is never bare.
    if not hotspots and g("hotspots") is not None:
        lines += ["", f"- **Hotspots:** {g('hotspots')}"]

    return "\n".join(lines) + "\n"


def onboarding_hub(*, tenant_id, project_id) -> dict:
    """Hub state across upload/adopt/register/index/gap (S-24) — the one read the onboarding
    screen needs; every step's action already exists as its own endpoint."""
    from apps.integrations.models import IntegrationConnection, SourceDocument
    from apps.projects.models import Project
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        docs = list(SourceDocument.objects.filter(
            tenant_id=tenant_id, project_id=project_id).order_by("-created_at"))
        pages_registered = Artifact.objects.filter(
            tenant_id=tenant_id, project_id=project_id, sor="confluence").count()
        issues_registered = sum(
            1 for w in WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id)
            if (w.external_ref or {}).get("sor") == "jira"
        )
        intel_artifact = Artifact.objects.filter(
            tenant_id=tenant_id, project_id=project_id, type="codebase_intelligence"
        ).order_by("-created_at").first()
        connected = {
            cap: IntegrationConnection.objects.filter(
                tenant_id=tenant_id, capability=cap).first()
            for cap in ("docstore", "tasktracker", "designsource")
        }

    gap = read_gap_report(tenant_id=tenant_id, project_id=project_id)
    return {
        "upload": [{"id": str(d.id), "filename": d.filename, "status": d.status} for d in docs],
        "adopt": [{"id": str(d.id), "filename": d.filename}
                 for d in docs if d.status == SourceDocument.Status.EXTRACTED],
        "register": {
            "docstore_connected": bool(
                connected["docstore"] and connected["docstore"].is_configured),
            "tasktracker_connected": bool(
                connected["tasktracker"] and connected["tasktracker"].is_configured),
            "designsource_connected": bool(
                connected["designsource"] and connected["designsource"].is_configured),
            "pages_registered": pages_registered, "issues_registered": issues_registered,
        },
        "adopt_types": adoptable_type_choices(),
        "index": {
            "status": "indexed" if intel_artifact else "not_started",
            "artifact_id": str(intel_artifact.id) if intel_artifact else None,
        },
        "gap": {"ready": True, "resume_phase": gap["resume_phase"]} if gap else {"ready": False},
    }
