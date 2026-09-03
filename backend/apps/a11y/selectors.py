"""What makes two references to an element the *same* element (QA-12a).

Three things now key off a selector — the scanner failure's identity (QA-06), the candidate row
it was stored under (QA-11b) and the finding fingerprint that decides whether a problem is the
one we saw last week — so the rule for comparing two of them belongs in one place rather than
being re-spelled in each.

**Deliberately not a CSS parser.** `A11yRuleFailure`'s identity has been textual since QA-06,
and this keeps it that way: whitespace is collapsed and nothing else is touched. Two spellings
that differ by more than spacing are treated as two elements, which is the safe direction —
showing a reviewer one element twice is an annoyance, and merging two different elements into
one hides a defect.
"""
from __future__ import annotations

import re

#: The shape ingest writes when a capture gave an element no selector of its own
#: (`ingest_screen`: `element.selector or f"{route}#{index}"`). It locates the element by its
#: position on the page, which is a real handle and a fragile one — see `is_positional`.
_POSITIONAL = re.compile(r"#\d+$")


def normalise(selector) -> str:
    """A selector reduced to what makes it that selector — whitespace collapsed."""
    return " ".join(str(selector or "").split())


def is_positional(selector, route) -> bool:
    """True when this selector is the platform's own positional fallback, not the page's.

    Such a finding is keyed on where the element *sat*, so anything that reorders the page
    breaks the match and the same problem is recorded twice. It is still recorded — a finding
    with a weak handle is worth far more than no finding — but it is flagged, so a reviewer
    seeing an apparent duplicate can tell why, and so nothing downstream treats "this is the
    same problem" as equally certain for it.

    **What this deliberately does NOT do**, and it is the case I expect to matter more: it does
    not judge a selector the *page* gave us as volatile. A hashed CSS class or a long
    `nth-child` chain churns between builds and would record a new finding each time — but
    which patterns are actually volatile is a guess until the rules have met real applications,
    and a wrong guess merges two elements that are not the same one. Left for QA-09/QA-10 to
    settle with measurements rather than settled here with an opinion.
    """
    text = normalise(selector)
    prefix = normalise(route)
    if not text or not prefix:
        return False
    return text.startswith(f"{prefix}#") and bool(_POSITIONAL.search(text))
