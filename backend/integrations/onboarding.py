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

import base64
import binascii
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


#: Attachment media types worth handing to the vision pass. A page's other attachments (a linked
#: spreadsheet, a PDF) are not page renders and would only bloat the payload.
_VISION_IMAGE_MIMES = ("image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp")


def ingest_confluence_page(*, tenant_id, project_id, page_id, artifact_type="document",
                           docstore=None, object_store=None) -> dict:
    """The Confluence sibling of `ingest_source_document` (S3-6).

    A linked page used to be registered as a bare pointer: typed, published, counted by the gap
    report as evidence — and **empty to every agent**, because the live read-through that fills a
    Confluence body is wired only into the human preview panel. A phase could be marked complete
    on a document nothing could read.

    Rather than teach the agent path to read Confluence, this gives a linked page the same
    `SourceDocument` an upload gets. Everything downstream then applies unchanged and un-rewritten:
    the adopt gate, one artifact registered at **v1**, the vision pass over its images, the
    content-loss guard, the honest fidelity badge, and retry. None of that machinery was ever
    upload-specific — it keys off the source document.

    **Idempotent by page id.** Re-linking a page updates the existing document in place instead of
    minting a second one, which would otherwise adopt into a second artifact and re-create exactly
    the duplicate-registry problem the upload flow was restructured to remove.

    Content is **snapshotted** here, not read live (team decision, 2026-07-29): vision needs
    durable images to transcribe and the content-loss guard needs a prior version to measure
    against, and a live read gives neither — besides making every agent read depend on Atlassian
    being reachable at that moment.
    """
    from apps.integrations.models import SourceDocument
    from apps.projects.models import Project
    from apps.tenancy.context import tenant_context
    from integrations.confluence_body import confluence_storage_to_markdown
    from storage import content_hash

    store = _object_store(object_store)
    if docstore is None:
        docstore = get_capability(tenant_id, "docstore")

    page = docstore.get_page(page_ref=str(page_id))
    body, referenced = confluence_storage_to_markdown(page.body_html or "")
    title = page.title or f"Confluence page {page_id}"

    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        src = next(
            (d for d in SourceDocument.objects.filter(tenant_id=tenant_id, project_id=project_id)
             if str((d.provenance or {}).get("confluence_page_id") or "") == str(page_id)),
            None,
        )
        if src is None:
            src = SourceDocument.objects.create(
                tenant_id=tenant_id, project=project, filename=title,
                mime="text/confluence-storage",
                status=SourceDocument.Status.EXTRACTING,
            )
        else:
            src.filename = title
            src.status = SourceDocument.Status.EXTRACTING
            src.save(update_fields=["filename", "status", "updated_at"])
    src_id = str(src.id)

    # Keep the untouched storage body as the "original", the way an upload keeps its file — it is
    # what a human is shown when they ask to see the source.
    src_key = f"onboarding/{tenant_id}/{project_id}/{src_id}/source/{page_id}.xhtml"
    store.put(src_key, (page.body_html or "").encode("utf-8"))

    # A Confluence page carries its diagrams as ATTACHMENTS, not inline — so the images the vision
    # pass reads have to be fetched one by one. Best-effort per image: one unreadable attachment
    # must not cost the page.
    page_images: list[dict] = []
    try:
        attachments = docstore.list_attachments(page_ref=str(page_id))
    except Exception:  # noqa: BLE001 — a page with unreadable attachments still ingests its text
        attachments = []
    # Images the body actually references come first and in document order; anything else attached
    # to the page follows, since a diagram is sometimes attached without an inline reference.
    order = {name: i for i, name in enumerate(referenced)}
    attachments.sort(key=lambda a: order.get(a.get("title", ""), len(order)))
    for i, att in enumerate(attachments, start=1):
        if (att.get("mime") or "").lower() not in _VISION_IMAGE_MIMES:
            continue
        try:
            raw = docstore.download_attachment(download_path=att.get("download_path", ""))
        except Exception:  # noqa: BLE001
            continue
        if not raw:
            continue
        name = att.get("title") or f"attachment{i}.png"
        vkey = f"onboarding/{tenant_id}/{project_id}/{src_id}/views/{name}"
        try:
            store.put(vkey, raw)
        except Exception:  # noqa: BLE001
            continue
        page_images.append({"name": name, "s3_key": vkey,
                            "mime": att.get("mime") or "image/png", "page": i})

    # Same honest fidelity marker the upload path derives (A4), from the same three cases.
    if body.strip():
        fidelity = "text"
    elif page_images:
        fidelity = "images_only"
        n = len(page_images)
        body = (
            f"> **This page is preserved.** “{title}” holds no readable text — its content is in "
            f"**{n} image{'s' if n != 1 else ''}** attached to the page, saved exactly as they "
            "are in Confluence.\n>\n"
            "> During onboarding, the AI reads each diagram and screen into structured text, so "
            "nothing is lost."
        )
    else:
        fidelity = "empty"
        body = (
            f"> **“{title}” was linked, but it has no content yet.**\n>\n"
            "> The page is empty in Confluence (an unfilled template counts as empty). Add its "
            "content there, then link it again."
        )

    body_key = f"onboarding/{tenant_id}/{project_id}/{src_id}/extracted.md"
    store.put(body_key, body)

    with tenant_context(tenant_id):
        src = SourceDocument.objects.get(id=src_id, tenant_id=tenant_id)
        src.s3_key = src_key
        src.status = SourceDocument.Status.EXTRACTED
        src.extracted_artifact_ids = []      # filled at adopt, exactly like an upload
        src.provenance = {
            "filename": title, "mime": "text/confluence-storage", "source_s3_key": src_key,
            "title": title, "fidelity": fidelity, "page_count": len(page_images),
            "page_images": page_images,
            "extracted_s3_key": body_key,
            "extracted_hash": content_hash(body.encode("utf-8")),
            "artifact_type": artifact_type,
            # What makes this document a Confluence page: the id is the idempotency key, and the
            # hash is what a later drift check would compare against the live page (the team's
            # reserved hybrid option).
            "origin": "confluence",
            "confluence_page_id": str(page_id),
            "confluence_url": page.url,
            "confluence_version": page.version,
        }
        src.save(update_fields=["s3_key", "status", "extracted_artifact_ids", "provenance",
                                "updated_at"])
        tools.log_event(tenant_id, "onboarding", "source_document.extracted", "source_document",
                        src_id, {"filename": title, "fidelity": fidelity,
                                 "origin": "confluence", "page_id": str(page_id)})

    return {"source_document_id": src_id, "status": "extracted", "artifact_ids": [],
            "title": title, "fidelity": fidelity, "page_count": len(page_images)}


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
            "That isn't a document type the platform can adopt. Choose one from the list."
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
            # Screen Words group 5. "(status=extracting)" put the stored state in brackets.
            if src.status == "adopted":
                raise OnboardingError("This document has already been adopted.")
            raise OnboardingError(
                "This document isn't ready to adopt yet — it is still being read, or "
                "reading it failed. Wait for it to finish, or upload it again."
            )
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
            # Screen Words group 3: named role, no internal user id. The check above accepts a
            # project admin and a workspace admin as well, so the sentence says so — it used to
            # name only `product_owner` and so was wrong about who could help.
            from apps.labels import role_label

            raise OnboardingRoleError(
                f"Only the {role_label('product_owner')} on this project, or an admin, "
                "can adopt documents."
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

    jql = f'project = "{project_key}"' if project_key else ""
    hits = tasktracker.search(jql=jql) if jql else []
    # S3-15: what Jira SAYS it has, so a partial import can admit it. -1 = Jira wouldn't answer;
    # the caller then reports a plain count rather than inventing a total.
    available = tasktracker.count(jql=jql) if (jql and hasattr(tasktracker, "count")) else -1

    # Read every matching issue, INCLUDING ones already registered. Re-import is a reconcile, not
    # an append: reading only the new keys would leave anything imported before this fix
    # permanently parentless, since a work item's parent is resolved here and nowhere else.
    # `get_issue` on a known key is a cheap read and creates nothing.
    fetched = [tasktracker.get_issue(issue_ref=hit.key) for hit in hits]

    registered_issues: list[str] = []
    repaired_descriptions = 0
    by_key: dict[str, object] = {}
    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        by_key = {
            (w.external_ref or {}).get("id"): w
            for w in WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id)
            if (w.external_ref or {}).get("sor") == "jira"
        }
        for issue in fetched:
            if issue.key in existing_issues:
                continue        # already registered — never recreate (spec §6)
            wi = WorkItem.objects.create(
                tenant_id=tenant_id, project=project,
                type=_ISSUE_TYPE.get(issue.issue_type, "task"), title=issue.summary,
                # The issue's body IS the specification. Dropping it left every imported item a
                # bare title, so the build agent had to invent the requirement it was meant to
                # implement — and nothing anywhere said the spec had gone missing.
                description=issue.description or "",
                state=WorkItem.State.ACCEPTED,
                external_ref={"sor": "jira", "id": issue.key, "url": issue.url},
            )
            by_key[issue.key] = wi
            tools.log_event(tenant_id, "onboarding", "issue.registered", "work_item",
                            str(wi.id), {"issue": issue.key})
            registered_issues.append(issue.key)

        # S3-15: carry Jira's hierarchy across. `get_issue` always returned `parent_ref` and the
        # import threw it away, so an imported backlog was a flat pile of subtasks sitting beside
        # the Epics and Stories they belong to, unrelated. Runs over every fetched issue, so a
        # re-import also repairs rows imported before this existed. Only ever SETS a missing
        # parent — a parent edited in the platform is not overwritten by Jira, and an issue whose
        # parent lives outside this project simply stays top-level rather than erroring.
        for issue in fetched:
            child = by_key.get(issue.key)
            parent = by_key.get(issue.parent_ref) if issue.parent_ref else None
            if child is not None and parent is not None and child.parent_id is None:
                child.parent = parent
                child.save(update_fields=["parent", "updated_at"])

        # Backfill descriptions the same way, and for the same reason: the create loop above
        # SKIPS an issue that is already registered, so a re-import would never repair a backlog
        # imported before the description was read — the user would re-run the import, see
        # "0 new issues", and still have 68 specification-less work items.
        # Only ever FILLS AN EMPTY one: a description edited in the platform is the human's, and
        # Jira must not overwrite it.
        for issue in fetched:
            wi = by_key.get(issue.key)
            if wi is not None and issue.description and not (wi.description or "").strip():
                wi.description = issue.description
                wi.save(update_fields=["description", "updated_at"])
                repaired_descriptions += 1
        if repaired_descriptions:
            tools.log_event(tenant_id, "onboarding", "issues.descriptions_backfilled", "project",
                            str(project_id), {"count": repaired_descriptions})

    return {
        "registered_issues": registered_issues,
        "descriptions_backfilled": repaired_descriptions,
        "tasktracker_connected": True,
        # Everything the UI needs to tell the truth about a partial import.
        "issues_available": available,
        "issues_seen": len(hits),
        "truncated": available >= 0 and len(hits) < available,
    }


def _decode_confluence_tiny_code(code: str) -> str | None:
    """Decode a Confluence "tiny link" code (`/wiki/x/AYAkAQ`) back into its page id (S3-10).

    That short form is what the *Copy link* button hands you in the current editor, so it is the
    link a user is most likely to paste — and it is not opaque: the code is base64 of the page id
    as little-endian bytes, with `=` padding dropped. `AYAkAQ` → `01 80 24 01` → 19169281.

    Confluence swaps `/`→`-` and `+`→`_`, which is the OPPOSITE of Python's urlsafe alphabet, so
    both mappings are attempted — a code containing neither character (the common case) decodes
    identically either way, and trying both costs nothing.
    """
    code = (code or "").strip()
    if not code or len(code) > 16:
        return None
    for plus, slash in (("_", "-"), ("-", "_")):
        candidate = code.replace(plus, "+").replace(slash, "/")
        candidate += "=" * (-len(candidate) % 4)
        try:
            data = base64.b64decode(candidate, validate=True)
        except (ValueError, binascii.Error):
            continue
        page_id = int.from_bytes(data, "little")
        if page_id > 0:
            return str(page_id)
    return None


def _parse_confluence_page_id(raw: str) -> str | None:
    """Extract a Confluence page id from a pasted link or a bare id (B3-4). Handles Cloud
    (`/wiki/spaces/<SPACE>/pages/<id>/<slug>` or `.../pages/<id>`), Server/DC
    (`viewpage.action?pageId=<id>`) and "tiny" share links (`/wiki/x/<code>`, decoded locally —
    see `_decode_confluence_tiny_code`); a bare numeric id passes through. Returns `None` if no id
    can be found — the caller then shows a "paste the full URL or the page ID" error."""
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
    # Tiny share link: .../wiki/x/<code> (the `x` segment is what marks it as one).
    for i, seg in enumerate(segments):
        if seg == "x" and i + 1 < len(segments):
            return _decode_confluence_tiny_code(segments[i + 1])
    return None


def link_confluence_pages(*, tenant_id, project_id, links, docstore=None,
                          object_store=None) -> dict:
    """B3-4 / S3-6 — bring user-provided Confluence pages in as **source documents** awaiting
    adoption. Each `links` row = `{"page": <url-or-id>, "type": <canonical lifecycle type>}`.

    **This no longer registers an artifact.** It used to: a linked page became a published, typed
    registry row on the spot. That row was a pointer with no body, and the read-through that fills
    a Confluence body is wired only into the human preview — so the gap report counted the page as
    phase evidence while every agent opening it read an empty string (S3-6).

    A link now does exactly what an upload does: snapshot the content into a `SourceDocument` and
    stop, leaving the human to review the extraction and adopt it. Adoption is the ONLY place an
    artifact is created — one per document, at v1 — which is the same invariant the upload flow was
    restructured to hold (PB-7). Registering here as well would put two artifacts behind one page.

    Idempotent by page id: re-linking re-snapshots the same source document rather than making a
    second one. Per-row errors are collected, not raised, so one bad link doesn't fail the batch.
    """
    from apps.projects.models import Project
    from apps.tenancy.context import tenant_context

    if docstore is None:
        # No docstore connector → CapabilityUnavailable, mapped to a friendly 4xx at the view.
        docstore = get_capability(tenant_id, "docstore")

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope

    linked: list[dict] = []
    errors: list[dict] = []
    for row in links:
        raw = (row or {}).get("page", "")
        # The type is now declared at ADOPT, the way an upload declares it — so a link does not
        # have to carry one. When it does (an API caller, or a pre-classified batch) it is
        # validated and pre-selects the adopt dropdown; when it doesn't, the document waits as a
        # generic `document` exactly as a freshly uploaded file does.
        target_type = (row or {}).get("type", "") or "document"
        if target_type != "document" and target_type not in ADOPTABLE_ARTIFACT_TYPES:
            errors.append({"page": raw, "error": f"unknown type {target_type!r}"})
            continue
        page_id = _parse_confluence_page_id(raw)
        if not page_id:
            errors.append({"page": raw,
                           "error": "couldn't find that page — paste the full URL or the page ID"})
            continue
        try:
            out = ingest_confluence_page(
                tenant_id=tenant_id, project_id=project_id, page_id=page_id,
                artifact_type=target_type, docstore=docstore, object_store=object_store,
            )
        except Exception:  # noqa: BLE001 — per-row error; don't fail the batch
            errors.append({"page": raw, "error": "couldn't read that page from Confluence"})
            continue
        linked.append({"page_id": page_id, "source_document_id": out["source_document_id"],
                       "type": target_type, "title": out["title"],
                       "fidelity": out["fidelity"], "page_count": out["page_count"],
                       # No artifact exists yet, and that is the point — adoption makes it.
                       "artifact_id": None, "status": "awaiting_adoption"})

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
    # Implementation is evidenced by the CODE, which is not a document — so the artifact that
    # stands for it is the code-intelligence report measured from the repository. This used to be
    # `("code",)`, a type nothing anywhere registers (S5-23): the entry was inert, the phase's
    # evidence list was always empty, and its status came solely from the `intel_present` flag.
    # Naming the real artifact makes the assessment cite what it actually relied on. Adoption is
    # still blocked for this phase (_NON_ADOPTABLE_PHASES) — a running codebase is proven from
    # git, never from an uploaded file.
    ("implementation", "7. Implementation", ("codebase_intelligence",)),
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


def _phase_label(phase: str | None) -> str:
    """The human label for a lifecycle phase key, from the ONE place the lifecycle is defined.
    Served to the UI (S5-7) so no client has to keep its own key→label map: the frontend's map was
    keyed `01_ideation` while this module emits the bare `ideation`, every lookup missed, and the
    Gap report screen rendered raw slugs. Numbering is stripped ("5. UX Design" -> "UX Design")
    because the report already shows the phases in order."""
    if not phase:
        return ""
    for key, label, _types in _LIFECYCLE:
        if key == phase:
            return label.split(". ", 1)[-1]
    return phase.replace("_", " ").title()


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
            type_label = _humanize_type(t)
            # The phase suffix exists to disambiguate ("ADR (Architecture)"). When the type IS
            # the phase it disambiguates nothing and reads as a mistake — "Ideation (Ideation)",
            # "PRD (PRD)". Drop the suffix in that case.
            option_label = (type_label if type_label.casefold() == phase_label.casefold()
                            else f"{type_label} ({phase_label})")
            choices.append({
                "value": t,
                "type_label": type_label,
                "phase": phase,
                "phase_label": phase_label,
                "label": option_label,
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
#
# `a11y_judging_carrier` is not an onboarding object and lives in `apps.a11y.aipass`; it is
# listed here because this is where the platform keeps the one definition of "carrier", and two
# lists would be two answers. It hosts the accessibility judge, which cannot run on the story:
# the story's own run is live for the whole build and `_guard_no_active_run` would refuse it.
#
# `a11y_journey_carrier` is the same shape one level along (G6b): one per keyboard journey,
# because the same rule that stops the judge running on the story stops a second journey
# running on the first journey's work item — so ticking three would have started one.
CARRIER_SOURCES = ("onboarding_carrier", "vision_carrier", "a11y_judging_carrier",
                   "a11y_journey_carrier")


def carrier_q(prefix: str = ""):
    """The `Q` that matches a CARRIER work item, for `.exclude(...)` on any queryset that reaches
    a WorkItem. `prefix` is the relation path to the work item ("" when the queryset IS work
    items, "work_item__" from Run/Approval/Clarification).

    The `has_key` half is LOAD-BEARING — do not "simplify" it away (S3-13). Without it this
    reduces to `external_ref__source__in=(…)`, and for a work item whose external_ref carries no
    `source` key at all — every Jira import, `{"sor": "jira", "id": "ST-447"}` — Postgres
    evaluates `NULL IN (…)` to NULL, `NOT NULL` to NULL, and drops the row. The backlog went
    empty for EVERY project (32 → 0 on one, 152 → 8 on another), taking Phases & Runs, Gates,
    Clarifications and Task Breakdown with it. Exclude only when the key EXISTS and names a
    carrier; anything else stays visible.
    """
    from django.db.models import Q

    return (Q(**{f"{prefix}external_ref__has_key": "source"})
            & Q(**{f"{prefix}external_ref__source__in": CARRIER_SOURCES}))

#: Run statuses that mean a headless onboarding step is still in flight. APPROVED is absent on
#: purpose: an auto-approved run never sits in it, and a run that somehow did is finishing, not
#: waiting on the user.
_LIVE_RUN_STATUSES = ("pending", "running", "awaiting_gate")


_IDLE_STEP_STATE = {"running": False, "run_id": None, "question": None, "approval_id": None}


def onboarding_step_state(*, tenant_id, project_id, agent_key, repo_id=None) -> dict:
    """Live state of ONE onboarding step (Index code / Gap report), for the hub.

    These steps run on a carrier work item hidden from the backlog and from Phases & Runs, so the
    Onboarding hub is the ONLY place their progress can be seen. Without this the hub had no
    "running" state at all and the button reverted the instant the POST returned 202, so a
    25-minute agent run looked like a no-op.

    Three states the user must be able to tell apart:
      * `running` alone — the agent is working; nothing to do.
      * `question` — the agent called `ask_human` and is blocked; the user must answer.
      * `approval_id` — the run finished and is waiting at its GATE (S5-8). Index code is headless
        and never reaches this, but the Gap report is gated by design, and without this the hub
        showed "working…" forever while it was really waiting on the user. `running` stays true
        because the run is not finished — but a hub that only reads `running` would strand it.

    Read-only — never creates a carrier (that is `ensure_onboarding_work_item`'s job).
    """
    from apps.clarifications.models import Clarification
    from apps.gates.models import Approval
    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        carrier = WorkItem.objects.filter(
            tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.EPIC,
            external_ref__source="onboarding_carrier",
            external_ref__repo_id=str(repo_id) if repo_id else None,
        ).first()
        if carrier is None:
            return dict(_IDLE_STEP_STATE)
        run = (
            Run.objects.filter(
                tenant_id=tenant_id, work_item=carrier, agent_spec__key=agent_key,
                status__in=_LIVE_RUN_STATUSES,
            ).order_by("-created_at").first()
        )
        if run is None:
            return dict(_IDLE_STEP_STATE)
        pending = (
            Clarification.objects.filter(
                tenant_id=tenant_id, run_id=run.id, status=Clarification.Status.PENDING,
            ).order_by("created_at").first()
        )
        approval = (
            Approval.objects.filter(
                tenant_id=tenant_id, run_id=run.id, decision="pending",
            ).order_by("created_at").first()
            if run.status == Run.Status.AWAITING_GATE else None
        )
        return {
            "running": True,
            "run_id": str(run.id),
            "question": ({"id": str(pending.id),
                          "count": len(pending.questions or [])} if pending else None),
            "approval_id": str(approval.id) if approval else None,
        }


#: Artifact types that are a RUN's own record rather than a project deliverable, and so are hidden
#: from the registry list — the same reasoning that hides the carrier work items above.
#: `document_vision` is the phase blob the platform registers for every run, holding the agent's
#: closing message. For a vision run the deliverable is the DOCUMENT the agent rewrote; the blob
#: sitting beside it made one uploaded file read as two published artifacts, which is precisely
#: the duplication adopt-time registration was meant to end. It is still stored, still on the run,
#: and still what the run console reads — it just isn't a thing the user owns.
RUN_RECORD_ARTIFACT_TYPES = ("document_vision",)


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
            # Just the filename: the platform names a run's own artifact
            # "{phase label} — {work item title}", so carrying the phase in the title too
            # produced "Document vision — Document vision — 09_Security.pdf".
            state=WorkItem.State.ACCEPTED, title=filename,
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
    # Non-document evidence: a backlog proves Task Breakdown, code intelligence proves the code
    # exists. There used to be a second `weak` flag here meant to express "code exists but is
    # unverified against the docs" — but it was a strict subset of this one, so the branch it
    # guarded was unreachable and Implementation was never once assessed `partial` (S5-22). It is
    # gone rather than switched on: making Implementation permanently partial would park every
    # brownfield project's resume point on it forever, which is worse than the honest reading —
    # the code is there, and whether it matches the docs is Code Review's question, not this one.
    strong = (phase == "task_breakdown" and has_backlog) or \
             (phase == "implementation" and intel_present)
    if published or strong:
        status = "complete"
    elif evidence:
        status = "partial"
    else:
        status = "missing"
    return status, evidence


def _resolvable_artifact_ids(tenant_id, project_id, ids) -> list[str]:
    """The subset of `ids` that are real artifacts of this project, de-duplicated and capped.

    Two filters, both load-bearing when the caller is an agent: a value that is not a UUID never
    reaches the database (Django raises `ValidationError` from the field, not a lookup miss), and
    a well-formed id belonging to another project is not this report's provenance.
    """
    import uuid

    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    candidates: list[str] = []
    for raw in dict.fromkeys(str(i) for i in ids if i):
        try:
            uuid.UUID(raw)
        except (ValueError, AttributeError, TypeError):
            continue
        candidates.append(raw)
    if not candidates:
        return []
    with tenant_context(tenant_id):
        real = set(
            Artifact.objects.filter(
                tenant_id=tenant_id, project_id=project_id, id__in=candidates[:200]
            ).values_list("id", flat=True)
        )
    return [c for c in candidates[:200] if uuid.UUID(c) in real]


def write_gap_report_artifact(
    *, tenant_id, project_id, phases, resume, blockers, intel_present,
    evidence_ids=(), object_store=None, run_id=None,
) -> dict:
    """Render + persist the canonical draft `gap_report` artifact and return the REST-shaped
    result. This is the ONE writer of the `external_ref` shape that `read_gap_report` + the whole
    UI depend on — shared by the deterministic `build_gap_report` AND the agent path's
    `submit_gap_report` tool, so neither can emit a shape the reader can't parse.

    `phases` is the canonical list [{phase, label, status, evidence:[...]}]; `evidence_ids` are
    the artifact ids the report derives from (trace edges).

    `run_id` binds the report to the agent run that reasoned it (S5-3), and is None on the
    deterministic REST path, which has no run. It is what makes the report count as the run's work
    product: `verify_writes` and `publish_artifacts` both filter on `run_id`, so an unbound report
    failed write-completeness and could never be published by its gate."""
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
    # "Code intelligence: not run" means something different when there is no repository to run
    # it against — then it is *not applicable*, and telling the reader to go and run it is noise.
    from apps.projects.models import Repository
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        has_repo = Repository.objects.filter(
            tenant_id=tenant_id, project_id=project_id).exists()
    body = _render_gap_report(render_phases, resume_label, blockers, intel_present, has_repo)
    body_key = f"onboarding/{tenant_id}/{project_id}/gap_report.md"
    store.put(body_key, body)
    # ALWAYS a title. `register_artifact`'s own contract tells agents to pass one, and the
    # platform was registering this one blank — so the report a Product Owner opens at the gate,
    # and the row it occupies in the registry, had no name at all (observed on run 448b8d21).
    # Name it for what it decides, so it reads as itself in a list of twenty artifacts.
    title = f"Gap Report — resume at {_phase_label(resume) or resume}"
    report = tools.register_artifact(
        tenant_id, project_id, run_id, phase="onboarding", type="gap_report", title=title,
        sor="internal", content_hash=content_hash(body.encode("utf-8")), s3_key=body_key,
        external_ref={"source": "onboarding", "resume_phase": resume,
                      "phases": [{"phase": p["phase"], "label": p["label"], "status": p["status"],
                                 "evidence": p.get("evidence", [])} for p in phases],
                      "blockers": blockers, "intel_present": intel_present},
    )
    # Only link evidence that RESOLVES. An agent citing an artifact id it invented is not
    # hypothetical — ids are exactly the kind of token a model reconstructs from memory — and an
    # unresolvable one used to raise straight out of `add_trace_edge` (a non-UUID string fails
    # Django's field validation), taking the whole submitted report down with it. Losing a
    # provenance link is a small, visible loss; losing the entire assessment because one id was
    # wrong is not. Resolve first, link what's real, keep the report.
    linked = _resolvable_artifact_ids(tenant_id, project_id, evidence_ids)
    for aid in linked:
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
        # Carriers are EXCLUDED, and that exclusion is load-bearing (S5-27). Task Breakdown is
        # assessed from the backlog, not from a document — and every onboarding/vision carrier is
        # created as an `epic`. Counted, they made `has_backlog` true on any project that had ever
        # run an onboarding step: clicking Index code was enough, and the gap report even corrupted
        # its OWN input, because `trigger_onboarding_agent` creates the carrier before the run
        # starts. Task Breakdown then reported Complete for a project with no backlog at all, and
        # the resume point skipped past the phase the team actually needed next.
        work_items = list(
            WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id)
            .exclude(carrier_q())
        )

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


#: Phases whose evidence is never a document, so "generate it via its phase agent" is the wrong
#: advice: you cannot author your way out of a missing codebase or an absent review history
#: (S5-28). The advice also depends on whether code intelligence has ALREADY run — telling someone
#: to go and index a repo that is already indexed is the kind of wrong-but-confident line this
#: whole audit was about. Keyed (phase, intel_present).
_NON_GENERATED_BLOCKER_ADVICE = {
    ("implementation", False): ("the codebase itself is the evidence — run **Index code** so the "
                                "platform can measure it, or link a repository if none is set."),
    ("implementation", True): ("code intelligence ran but found no codebase to attribute to this "
                               "project — check the linked repository is the right one."),
    ("code_review", False): ("evidenced by merge history and required checks — run **Index code** "
                             "first so there is history to read."),
    ("code_review", True): ("no review evidence found in the indexed history — if reviews happen "
                            "outside this repository, register that record; otherwise this phase "
                            "genuinely has not run yet."),
}


def _render_gap_report(phases, resume_label, blockers, intel_present, has_repo=True) -> str:
    icon = {"complete": "Complete", "partial": "Partial", "missing": "Missing"}
    resume_idx = next(
        (i for i, p in enumerate(phases) if p["status"] != "complete"), len(phases))
    # "Not run" is a status with nothing to do about it. Say what it means for THIS project and
    # what to do — or that there is nothing to do, when the project has no repository at all.
    if intel_present:
        intel_line = "available — Implementation and Code Review are assessed from measured code."
    elif not has_repo:
        intel_line = ("not applicable — no repository is linked to this project yet, so there "
                      "is no code to measure.")
    else:
        intel_line = ("**not run** — run **Index code** first. Until then Implementation and "
                      "Code Review cannot be assessed, and are reported as missing rather than "
                      "judged.")
    lines = [
        "# Onboarding Gap Report",
        "",
        "> Generated by the Onboarding Agent — what existed, what was registered, "
        "and what is still missing before the pipeline resumes.",
        "",
        f"**Code intelligence:** {intel_line}",
        f"**Recommended resume phase:** {resume_label}",
        "",
        "## Phase Completion Assessment",
        "",
        "| Phase | Status | Evidence |",
        "|-------|--------|----------|",
    ]
    # A phase AFTER the resume point with no evidence has not been reached yet — it is not a gap
    # the team failed to fill. Reporting six identical "Missing" rows to a team that legitimately
    # stopped at UX Design reads as six failures (S5-28).
    for i, p in enumerate(phases):
        label = ("Not started" if p["status"] == "missing" and i > resume_idx
                 else icon[p["status"]])
        lines.append(f"| {p['label']} | {label} | {p['evidence_count']} artifact(s) |")
    lines += ["", "## Blockers (resolve before resuming)", ""]
    by_phase = {p["phase"]: p.get("label", p["phase"]) for p in phases}
    lines += ([f"- **{by_phase.get(b, b)}** — "
               + _NON_GENERATED_BLOCKER_ADVICE.get(
                   (b, bool(intel_present)),
                   "no evidence found; generate it via its phase agent (gated), "
                   "or upload and adopt the existing source.")
               for b in blockers] or ["- None."])
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
            #
            # `label` is forwarded (S5-7). It was dropped here, so the frontend had to map phase
            # keys itself — against a list keyed `01_ideation`/`04_architecture` while this emits
            # the bare `ideation`/`ux_design`. Every lookup missed and the screen showed raw slugs
            # ("Resume at: task_breakdown"). The human label already exists in `external_ref`;
            # sending it is one key and kills the whole class of drift.
            {"phase": p["phase"], "label": p.get("label") or _phase_label(p["phase"]),
             "assessment": p["status"], "evidence": p.get("evidence", [])}
            for p in ext.get("phases", [])
        ],
        "resume_label": _phase_label(ext.get("resume_phase")),
        "blocking": ext.get("blockers", []),
    }


#: The evidence keys `read_gap_report` promises the UI. Anything else an agent invents is dropped.
_EVIDENCE_KEYS = ("artifact_id", "type", "sor", "status")


def _clean_evidence(raw) -> list[dict]:
    """Coerce an agent's `evidence` into the exact ref shape the deterministic path emits (S5-20).

    Only the list-ness used to be checked, so elements could be anything the model felt like —
    bare id strings, nested dicts, prose. The stored `external_ref` is a UI contract: whatever
    lands here is what every client renders, and the frontend has already been broken once by an
    evidence value it did not expect. Anything without a usable `artifact_id` is dropped rather
    than guessed at; an entry that is just the id string is accepted and normalized, because that
    is an obvious shorthand and the id is the only part that carries meaning.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:10]:                       # same cap the deterministic path uses
        if isinstance(item, str) and item.strip():
            out.append({"artifact_id": item.strip()})
        elif isinstance(item, dict) and item.get("artifact_id"):
            out.append({k: str(item[k]) for k in _EVIDENCE_KEYS if item.get(k) is not None})
    return out


def submit_agent_gap_report(
    *, tenant_id, project_id, phases, resume_phase=None, blockers=None, object_store=None,
    run_id=None,
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
            supplied[p["phase"]] = {
                "status": p["status"], "evidence": _clean_evidence(p.get("evidence")),
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
        object_store=object_store, run_id=run_id,
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


def _vendor_of(connection, capability: str) -> str | None:
    """The human name of the tool behind a capability — None until one is really connected.

    None is the important half: it is what stops a screen naming Jira to somebody who has not
    connected anything, which is the whole reason the onboarding step read wrong.
    """
    if connection is None or not connection.is_configured:
        return None
    from apps.integrations.catalog import vendor_label

    return vendor_label(capability, connection.connector)


def onboarding_hub(*, tenant_id, project_id) -> dict:
    """Hub state across upload/adopt/register/index/gap (S-24) — the one read the onboarding
    screen needs; every step's action already exists as its own endpoint."""
    from apps.integrations.models import IntegrationConnection, SourceDocument
    from apps.projects.models import Project, Repository
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
        docs = list(SourceDocument.objects.filter(
            tenant_id=tenant_id, project_id=project_id).order_by("-created_at"))
        # Count the linked PAGES, not artifacts with `sor="confluence"` (S3-6). A linked page is
        # now snapshotted into a source document and adopted like an upload, so its artifact is an
        # internal one holding the snapshot — the old query would report 0 however many pages were
        # linked, and the step would never look done.
        pages_registered = sum(
            1 for d in docs if (d.provenance or {}).get("origin") == "confluence"
        )
        issues_registered = sum(
            1 for w in WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id)
            if (w.external_ref or {}).get("sor") == "jira"
        )
        intel_artifact = Artifact.objects.filter(
            tenant_id=tenant_id, project_id=project_id, type="codebase_intelligence"
        ).order_by("-created_at").first()
        # Per-repo, because code intelligence is dispatched per repository (one carrier pinned to
        # each). The project-level `index.status` below stays as it was for back-compat.
        repo_rows = list(Repository.objects.filter(
            tenant_id=tenant_id, project_id=project_id).order_by("name"))
        intel_by_repo = {
            str(a.repo_id): a for a in Artifact.objects.filter(
                tenant_id=tenant_id, project_id=project_id, type="codebase_intelligence",
            ).order_by("created_at") if a.repo_id
        }
        connected = {
            cap: IntegrationConnection.objects.filter(
                tenant_id=tenant_id, capability=cap).first()
            for cap in ("docstore", "tasktracker", "designsource")
        }

    with tenant_context(tenant_id):
        from apps.a11y.baseline import IN_FLIGHT_STATUSES
        from apps.a11y.models import A11yBaselineAudit, A11yRoute

        a11y_routes = A11yRoute.objects.filter(
            tenant_id=tenant_id, project_id=project_id, enabled=True).count()
        # Counted apart, because the step used to count `judging` as run and then say "1 audit
        # run — open the report from Artifacts" while the audit was still going. There is no
        # report to open until the judging ends: the baseline is published when the judge run
        # closes, precisely so it never states a position that is still changing. So a finished
        # audit is what makes this step done, and one still going says that it is going.
        a11y_audits = A11yBaselineAudit.objects.filter(
            tenant_id=tenant_id, project_id=project_id,
            status=A11yBaselineAudit.Status.COMPLETE).count()
        a11y_running = A11yBaselineAudit.objects.filter(
            tenant_id=tenant_id, project_id=project_id,
            status__in=IN_FLIGHT_STATUSES).exists()

    gap = read_gap_report(tenant_id=tenant_id, project_id=project_id)
    # Live state of the two headless steps. Outside the block above because each opens its own
    # tenant_context; cheap (one indexed lookup per repo) and only this screen asks for it.
    index_states = {
        str(r.id): onboarding_step_state(
            tenant_id=tenant_id, project_id=project_id,
            agent_key="00c_intelligent_context_extractor", repo_id=str(r.id),
        )
        for r in repo_rows
    }
    gap_state = onboarding_step_state(
        tenant_id=tenant_id, project_id=project_id, agent_key="00_onboarding",
    )
    return {
        # S3-14: `origin` lets the step say "9 documents uploaded · 2 pages linked" instead of
        # calling a linked Confluence page an upload. Additive and defaulted, so a project with no
        # linked pages — every greenfield one — reports "upload" for every row and reads exactly
        # as it did before.
        "upload": [{"id": str(d.id), "filename": d.filename, "status": d.status,
                    "origin": (d.provenance or {}).get("origin") or "upload"} for d in docs],
        "adopt": [{"id": str(d.id), "filename": d.filename}
                 for d in docs if d.status == SourceDocument.Status.EXTRACTED],
        "register": {
            "docstore_connected": bool(
                connected["docstore"] and connected["docstore"].is_configured),
            "tasktracker_connected": bool(
                connected["tasktracker"] and connected["tasktracker"].is_configured),
            "designsource_connected": bool(
                connected["designsource"] and connected["designsource"].is_configured),
            # Which vendor is actually behind each capability, once one is. The step offers to
            # connect a *capability* (#9 — capabilities, not vendors), because before anything is
            # connected the platform has no business assuming Jira. Afterwards it does know, and
            # "Import task tracker backlog" would be worse than naming the tool the user just
            # connected — so the step says "Import Jira backlog" because it was told, not because
            # it was hardcoded, and it will say the right thing on the day a second vendor exists.
            # None when nothing is connected, which is exactly when the UI must not name a vendor.
            "docstore_vendor": _vendor_of(connected["docstore"], "docstore"),
            "tasktracker_vendor": _vendor_of(connected["tasktracker"], "tasktracker"),
            "designsource_vendor": _vendor_of(connected["designsource"], "designsource"),
            "pages_registered": pages_registered, "issues_registered": issues_registered,
        },
        "adopt_types": adoptable_type_choices(),
        # Where the accessibility step stands (task 8a). A brownfield project's pages are the
        # one thing the platform cannot discover for itself — it has no access to the running
        # application, deliberately — so the step is "have they told us, and has an audit run".
        # Both are counts rather than a stored flag: a flag would be a third thing to keep in
        # step with two facts that already exist.
        "a11y": {
            "routes_registered": a11y_routes,
            "audits_run": a11y_audits,
            # Both `running` and `status`, the same shape and the same reason as the Index code
            # step below: the tick and the button switch on `status`, while the line of text has
            # to be able to say "and another one is going right now" over the top of it.
            "running": a11y_running,
            "status": ("done" if a11y_audits else
                       "running" if a11y_running else
                       "ready" if a11y_routes else "not_started"),
        },
        "index": {
            "status": "indexed" if intel_artifact else "not_started",
            "artifact_id": str(intel_artifact.id) if intel_artifact else None,
            # Per-repo lifecycle the hub renders its button + message from. Deriving the UI from
            # THIS (server truth) rather than the POST's mutation result is what makes the
            # "working" message clear itself on completion and on a re-index — a mutation result
            # is set once and never clears, which is why the old message stuck forever.
            "repos": [
                {
                    "repo_id": str(r.id),
                    "name": r.name,
                    "status": ("running" if index_states[str(r.id)]["running"]
                               else "indexed" if str(r.id) in intel_by_repo
                               else "not_started"),
                    # Both `running` and `status` on purpose: the button switches on the tri-state
                    # `status`, while the progress/question line takes the same `{running,
                    # question}` shape as the gap step so ONE component renders both.
                    "running": index_states[str(r.id)]["running"],
                    "run_id": index_states[str(r.id)]["run_id"],
                    "question": index_states[str(r.id)]["question"],
                    "artifact_id": (str(intel_by_repo[str(r.id)].id)
                                    if str(r.id) in intel_by_repo else None),
                }
                for r in repo_rows
            ],
        },
        "gap": {
            # `resume_label` rides along with the key (S5-7) so no client keeps its own key→label
            # map — the one the frontend had was keyed differently and rendered raw slugs.
            **({"ready": True, "resume_phase": gap["resume_phase"],
                "resume_label": gap.get("resume_label") or "",
                # The report's own artifact, so the hub can link to the rendered document the way
                # the Index code step already links to its intelligence artifact (S5-19).
                "report_artifact_id": gap["gap_report_id"]}
               if gap else {"ready": False}),
            "running": gap_state["running"],
            "run_id": gap_state["run_id"],
            "question": gap_state["question"],
            # Non-null when the run is parked at its Product Owner gate (S5-8). The gap report is
            # gated by design, so without this the hub says "working…" for as long as the user
            # takes to approve — and gives them no way to reach the gate from here.
            "approval_id": gap_state["approval_id"],
        },
    }
