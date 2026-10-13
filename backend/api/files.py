"""Serving a stored body as a file, with a filename that cannot break the response.

Everything served from this platform is named after something a person or an agent typed: an
artifact's `title` (free text, 200 characters, authored by a phase agent), an uploaded document's
`filename`. Those strings end up inside an HTTP header, and a header is a line-oriented format with
quoting rules — so a title containing a newline, a quote or a non-ASCII character is not a cosmetic
problem. It is a broken response at best, and at worst a second header of the caller's choosing.

Before this module, all three file responses in the codebase built the header with an f-string and
no escaping at all. None of them had failed yet, which is exactly the kind of thing that stays true
until the day somebody names a document "Q3 report (final)".

Two headers are written for one filename, which is not belt-and-braces but RFC 6266:
`filename=` may only carry ASCII, and `filename*=` (RFC 5987) carries the real UTF-8 one. Browsers
that understand the second prefer it; everything else falls back to a readable transliteration
rather than mojibake or a rejected header.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

from django.http import HttpResponse

#: Long enough for any real document name, short enough to stay well inside the header limits that
#: proxies impose, and to survive being joined onto a deep download path by the operating system.
_MAX_STEM = 120

#: Characters a filename may never contain: path separators (a name is not a path), quotes and
#: backslashes (they terminate or escape the quoted-string the header uses), and the control
#: characters — CR and LF above all, which are what would end one header and begin another.
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
_WHITESPACE = re.compile(r"\s+")
_DASHES = re.compile(r"-{2,}")


def safe_filename(stem: str, *, extension: str = "", fallback: str = "document") -> str:
    """A filename built from text somebody else wrote.

    Keeps the name recognisable — this is the whole point of not falling back to a UUID — while
    removing everything that makes it dangerous or unusable. `extension` is given without its dot
    and is sanitised on the same terms, because it is derived from a content type that is itself
    partly agent-declared.
    """
    cleaned = _UNSAFE.sub(" ", stem or "")
    cleaned = _WHITESPACE.sub("-", cleaned.strip())
    # Em dashes and the like are legitimate in a title and awful in a filename — a human reading
    # `PRD—Spend-Export` cannot tell where the words break.
    cleaned = _DASHES.sub("-", cleaned.replace("—", "-").replace("–", "-"))
    cleaned = cleaned.strip("-. ")[:_MAX_STEM].strip("-. ")
    if not cleaned:
        cleaned = fallback
    ext = _UNSAFE.sub("", extension or "").strip(". ")
    return f"{cleaned}.{ext}" if ext else cleaned


def _ascii_fallback(name: str) -> str:
    """The same name with every character a legacy client can actually read.

    Transliterates rather than deletes: `Résumé.md` becomes `Resume.md`, not `Rsum.md`. Anything
    with no ASCII equivalent at all (a title written in Devanagari, say) would reduce to nothing, so
    the extension is kept and the stem falls back to a word rather than leaving a bare dot.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    folded = folded.replace('"', "").replace("\\", "")
    stem, _, ext = folded.rpartition(".")
    if not stem.strip("-. "):
        return f"document.{ext}" if ext else "document"
    return folded


def attachment_response(data: bytes, *, filename: str, content_type: str) -> HttpResponse:
    """Hand `data` over as a download called `filename`.

    The counterpart to the `inline` responses that show something in the page. `attachment` is the
    difference between a browser rendering a document and saving it, and it is the only header that
    makes "Download" mean download.
    """
    return _disposition(data, filename=filename, content_type=content_type, kind="attachment")


def inline_response(data: bytes, *, filename: str, content_type: str) -> HttpResponse:
    """Hand `data` over to be shown IN the page (an image, a page capture).

    Same filename safety; `inline` so the browser renders it instead of saving it. A test asserts on
    that word, because flipping it would turn every screenshot in the product into a download.
    """
    return _disposition(data, filename=filename, content_type=content_type, kind="inline")


def _disposition(data: bytes, *, filename: str, content_type: str, kind: str) -> HttpResponse:
    name = safe_filename(filename) if filename else "document"
    resp = HttpResponse(data, content_type=content_type or "application/octet-stream")
    resp["Content-Disposition"] = (
        f'{kind}; filename="{_ascii_fallback(name)}"; '
        f"filename*=UTF-8''{quote(name, safe='')}"
    )
    return resp


def artifact_filename(artifact, *, content_type: str) -> str:
    """What a downloaded artifact is called — `PRD-Spend-Export-v2.md`.

    Named after the document, never after its id. The standing rule is that no id reaches a client's
    screen, and a file called `3dab76d0-5dcf-473a-84be-9926aa0b8b59.md` sitting in somebody's
    Downloads folder is the same failure made permanent: a week later nobody can tell what it is.

    The title is agent-authored and may be blank, so it falls back to the type and phase — the same
    rule `_publish_docstore` already uses when it has to name a page. The version is included
    because downloading v1 and v2 of the same document is a normal thing to do and two files called
    `PRD-Spend-Export.md` is not a helpful answer to it.
    """
    from apps.labels import phase_label
    from integrations.preview import extension_for_content_type

    stem = (artifact.title or "").strip()
    if not stem:
        type_label = str(artifact.type or "document").replace("_", " ").title()
        where = phase_label(artifact.phase) or ""
        stem = f"{type_label} {where}".strip()
    version = getattr(artifact, "version", None)
    if version:
        stem = f"{stem}-v{version}"
    return safe_filename(stem, extension=extension_for_content_type(content_type),
                         fallback="document")
