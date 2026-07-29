"""Confluence **storage format** → clean markdown (S3-8).

Confluence does not store HTML. It stores its own XHTML dialect in which the meaningful content is
wrapped in `ac:`/`ri:` elements, and running that through a generic HTML-to-text pass produces real
content laced with machine noise. Measured on a real page before this module existed:

    ## Description
    #F4F5F7                                              <- a panel macro's background colour
    In a sentence or two, describe the purpose of this space.
    ## Project Tracker
    com.atlassian.confluence.project-linker … 3781a39a-…  <- macro internals
    page,whiteboard,database,blog 10 concise true         <- macro parameters

An agent reading that treats `#F4F5F7` as a requirement. Four pages sampled from a live space
carried 0, 3, 5 and 8 `<ac:structured-macro>` elements, so this is the normal case, not an edge.

Three judgements this module makes, none of them obvious:

1. **A macro parameter is not automatically noise.** `<ac:parameter ac:name="title">Not started
   </ac:parameter>` on a `status` macro is the whole content of that cell; `colour` beside it is
   presentation. So parameters are filtered by NAME (`_KEEP_PARAMS`), not dropped wholesale.
2. **Some macros have no content here at all.** A `recently-updated` or `project-linker` macro
   renders server-side; the storage format holds only its configuration. Emitting anything from
   those is emitting settings as prose, so they are dropped entire (`_DROP_MACROS`).
3. **Tables must survive as tables.** The generic extractor treats `<table>`/`<tr>` as block
   breaks, which flattens a requirements matrix into an unstructured run of lines. Here they are
   rendered as real markdown tables, so the relationships between cells reach the agent intact.

Embedded images are `<ac:image><ri:attachment ri:filename="…"/></ac:image>` — a reference, not
bytes. Each one is emitted as a markdown image and its filename recorded, so the ingest path knows
which attachments to download for the vision pass.

Stdlib only, matching `integrations.extract`.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

#: Macro parameters that carry content a reader needs. Everything else is presentation
#: (`colour`, `bgColor`, `width`, `layout`) or plumbing (`macro-id`, `schema-version`).
_KEEP_PARAMS = {"title"}

#: Macros whose storage form holds configuration rather than content — they are rendered by
#: Confluence at view time from live data. Their parameters read as gibberish in a transcript.
_DROP_MACROS = {
    "recently-updated", "contributors", "children", "pagetree", "project-linker",
    "livesearch", "detailssummary", "content-report-table", "blog-posts",
    "recently-updated-dashboard", "navmap", "labellist", "spacedetails",
    "create-from-template", "contentbylabel",
}

#: Presentational containers with nothing to say, plus elements holding pure configuration.
#: `ac:adf-attribute` is the newer-editor equivalent of a macro parameter — it is how a
#: project-linker extension leaked `com.atlassian.confluence.project-linker … 3781a39a-…` into a
#: transcript. Its subtree is always machine configuration, never prose.
#: `ac:task-id`/`ac:task-status` are checklist bookkeeping — left in, a task list transcribes as
#: "1 incomplete Type your task here".
#: `ac:placeholder` is the grey hint text an empty template shows in the editor ("Add action items
#: to close the loop…"). It is deliberately dropped: it is guidance addressed to a human author,
#: and an agent that ingests it reads instructions-to-the-writer as project requirements. Dropping
#: it also makes an unfilled template come back **empty**, which is the honest signal — the
#: existing `fidelity: empty` path then tells the user plainly that the page holds nothing yet.
_SKIP_TAGS = {"colgroup", "col", "script", "style", "head", "noscript", "template",
              "ac:adf-attribute", "ac:adf-parameter",
              "ac:task-id", "ac:task-status", "ac:placeholder", "ac:emoticon"}

#: Wrappers that exist only to hold other content — unwrap and keep going.
_TRANSPARENT = {
    "ac:rich-text-body", "ac:layout", "ac:layout-section", "ac:layout-cell",
    "ac:adf-extension", "ac:adf-content", "body", "html", "span", "font",
}

_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK = {"p", "div", "section", "article", "header", "footer", "blockquote"}


class _ConfluenceStorageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        #: filenames of attached images referenced by the body, in document order
        self.attachment_names: list[str] = []

        self._skip_depth = 0
        #: name of the macro being dropped + the depth at which the drop started
        self._drop_macro_depth = 0
        #: stack of open macro names, so a parameter knows which macro it belongs to
        self._macro_stack: list[str] = []
        #: inside <ac:parameter> at all — the flag that decides whether text is document text.
        #: Kept separate from `_param_name` because a DISCARDED parameter has no name, and
        #: keying only on the name let its text fall through into the body (`#F4F5F7`).
        self._in_parameter = False
        #: name of the parameter being KEPT (None while discarding one)
        self._param_name: str | None = None
        self._param_buf: list[str] = []
        #: code-block capture (<ac:plain-text-body> inside a code macro)
        self._in_plain_text = False
        self._plain_buf: list[str] = []
        #: table state — a stack so nested tables still render
        self._tables: list[dict] = []

    # ── output routing ──────────────────────────────────────────────
    def _emit(self, text: str) -> None:
        """Append to whatever is currently collecting: a table cell, else the document."""
        if self._drop_macro_depth or self._skip_depth:
            return
        if self._tables and self._tables[-1]["cell"] is not None:
            self._tables[-1]["cell"].append(text)
        else:
            self.parts.append(text)

    # ── tags ────────────────────────────────────────────────────────
    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k: (v or "") for k, v in attrs}

        if self._skip_depth:
            if tag in _SKIP_TAGS:
                self._skip_depth += 1
            return
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return

        # A dropped macro swallows everything inside it.
        if self._drop_macro_depth:
            if tag in ("ac:structured-macro", "ac:macro"):
                self._drop_macro_depth += 1
            return

        if tag in ("ac:structured-macro", "ac:macro"):
            name = a.get("ac:name", "")
            if name in _DROP_MACROS:
                self._drop_macro_depth = 1
                return
            self._macro_stack.append(name)
            return

        if tag == "ac:parameter":
            name = a.get("ac:name", "")
            self._in_parameter = True
            self._param_name = name if name in _KEEP_PARAMS else None
            self._param_buf = []
            return

        if tag == "ac:plain-text-body":
            self._in_plain_text = True
            self._plain_buf = []
            return

        # An embedded image: a REFERENCE to an attachment, not bytes.
        if tag == "ac:image":
            return
        if tag == "ri:attachment":
            fn = a.get("ri:filename", "")
            if fn:
                self.attachment_names.append(fn)
                self._emit(f"\n\n![{fn}](attachment:{fn})\n\n")
            return
        if tag == "ri:url":
            src = a.get("ri:value", "")
            if src:
                self._emit(f"\n\n![]({src})\n\n")
            return

        if tag in _TRANSPARENT:
            return

        # Tables — buffered so they can be rendered as markdown on close.
        if tag == "table":
            self._tables.append({"rows": [], "row": None, "cell": None, "header": False})
            return
        if self._tables:
            t = self._tables[-1]
            if tag == "tr":
                t["row"] = []
                return
            if tag in ("td", "th"):
                t["cell"] = []
                if tag == "th":
                    t["header"] = True
                return

        # Emphasis is often the ONLY structure a page has: a real requirements page authored in
        # the new editor came through with zero <h1>/<h2>/<h3> and 140 <strong> — its headings
        # were written as bold text. Dropping the markers flattened the whole document.
        if tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "code":
            self._emit("`")
        elif tag in _HEADINGS:
            self._emit("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self._emit("\n- ")
        elif tag == "ac:task":
            self._emit("\n- [ ] ")
        elif tag == "ac:task-list":
            self._emit("\n\n")
        elif tag in ("br", "hr"):
            self._emit("\n")
        elif tag in ("ul", "ol", "pre"):
            self._emit("\n\n")
        elif tag in _BLOCK:
            self._emit("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth and tag in _SKIP_TAGS:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return

        if self._drop_macro_depth:
            if tag in ("ac:structured-macro", "ac:macro"):
                self._drop_macro_depth -= 1
            return

        if tag in ("ac:structured-macro", "ac:macro"):
            if self._macro_stack:
                self._macro_stack.pop()
            return

        if tag == "ac:parameter":
            if self._param_name:
                text = " ".join("".join(self._param_buf).split())
                if text:
                    self._emit(text + " ")
            self._in_parameter = False
            self._param_name = None
            self._param_buf = []
            return

        if tag == "ac:plain-text-body":
            code = "".join(self._plain_buf).strip("\n")
            self._in_plain_text = False
            self._plain_buf = []
            if code:
                self._emit(f"\n\n```\n{code}\n```\n\n")
            return

        if self._tables:
            t = self._tables[-1]
            if tag in ("td", "th") and t["cell"] is not None:
                cell = " ".join("".join(t["cell"]).split())
                if t["row"] is None:
                    t["row"] = []
                t["row"].append(cell)
                t["cell"] = None
                return
            if tag == "tr" and t["row"] is not None:
                t["rows"].append(t["row"])
                t["row"] = None
                return
            if tag == "table":
                self._tables.pop()
                rendered = _render_table(t["rows"], t["header"])
                self._emit(rendered)
                return

        if tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "code":
            self._emit("`")
        elif tag in _HEADINGS:
            self._emit("\n")
        elif tag in _BLOCK:
            self._emit("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._drop_macro_depth:
            return
        if self._in_plain_text:
            self._plain_buf.append(data)
            return
        if self._in_parameter:
            # Kept parameter → buffer it; discarded one → drop it here, so a colour code can
            # never reach the document as if it were prose.
            if self._param_name:
                self._param_buf.append(data)
            return
        text = " ".join(data.split())
        # Confluence writes literal backslash-n between some block elements (seen between
        # `<ac:task>` siblings). It is source formatting, not text the page shows.
        text = text.replace("\\n", " ").strip()
        if text:
            self._emit(text + " ")


def _render_table(rows: list[list[str]], has_header: bool) -> str:
    """Rows → a markdown table. A table whose cells are all empty (a layout table, which
    Confluence also uses for page furniture) renders as nothing rather than an empty grid.

    `has_header` only tells us whether Confluence used `<th>`. Plenty of real pages do not: a live
    requirements page styled every header row as `<td>` with bold text inside. Markdown has no way
    to express a table WITHOUT a header, so emitting an empty header row there pushed the real
    column names ("Version | Date | Author") down into the body and left the table looking
    headerless. The first row is promoted instead — which is both what the author intended and how
    Confluence renders it.
    """
    rows = [r for r in rows if r]
    if not rows or not any(any(c for c in r) for r in rows):
        return "\n\n"
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]
    head, body = norm[0], norm[1:]
    out = ["", "| " + " | ".join(head) + " |", "|" + "|".join([" --- "] * width) + "|"]
    out.extend("| " + " | ".join(r) + " |" for r in body)
    return "\n\n" + "\n".join(out) + "\n\n"


def confluence_storage_to_markdown(storage_xhtml: str) -> tuple[str, list[str]]:
    """Convert one page's storage body to markdown.

    Returns `(markdown, attachment_filenames)` — the filenames being the images the body
    references, which the caller downloads so the vision pass can read them.
    """
    parser = _ConfluenceStorageParser()
    parser.feed(storage_xhtml or "")
    parser.close()
    text = "".join(parser.parts)

    # Confluence pads cell text with &nbsp;, which lands inside the emphasis markers as
    # `**Version **`. CommonMark does not accept a closing `**` preceded by whitespace, so that
    # renders as literal asterisks rather than bold. Pull the padding outside the markers.
    # Nothing here tries to strip "emphasis wrapping nothing": every pattern that catches `** **`
    # also matches the `**` … `**` BETWEEN two adjacent bold runs, and deleting those unbolds both.
    text = re.sub(r"\*\*[ \t]*([^\n*][^\n*]*?)[ \t]*\*\*", r"**\1**", text)
    text = re.sub(r"(?<!\*)\*[ \t]*([^\n*][^\n*]*?)[ \t]*\*(?!\*)", r"*\1*", text)

    # Inline tags split text into space-padded chunks, leaving gaps before punctuation.
    text = re.sub(r"[ \t]+([.,;:!?)])", r"\1", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip(), parser.attachment_names
