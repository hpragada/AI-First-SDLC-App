"""Jira descriptions: Atlassian Document Format → readable text.

Jira REST v3 returns an issue description as an ADF *tree*, never a string. Read naively you
get a dict; stringified you hand an agent a wall of JSON. These tests pin the conversion,
because a task's acceptance criteria are usually a bulleted list and losing the bullets loses
the shape of the requirement.
"""
from integrations.atlassian.tasktracker import _adf, _adf_to_text, _description_text
from integrations.types import Issue


def _doc(*content):
    return {"type": "doc", "version": 1, "content": list(content)}


def _para(*text):
    return {"type": "paragraph",
            "content": [t if isinstance(t, dict) else {"type": "text", "text": t}
                        for t in text]}


def test_plain_paragraphs_survive():
    out = _description_text(_doc(_para("Every query must filter by user_id."),
                                 _para("Reject cross-user reads.")))
    assert out == "Every query must filter by user_id.\nReject cross-user reads."


def test_acceptance_criteria_keep_their_bullets():
    """The single most common shape of a real task description. Flattening the list into one
    run-on line would blur three separate criteria into one sentence."""
    out = _description_text(_doc(
        _para("Acceptance criteria:"),
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [_para("Filter every read by user_id")]},
            {"type": "listItem", "content": [_para("Return 404, never 403, on another user's row")]},
            {"type": "listItem", "content": [_para("Cover it with a characterisation test")]},
        ]},
    ))
    assert "- Filter every read by user_id" in out
    assert "- Return 404, never 403, on another user's row" in out
    assert "- Cover it with a characterisation test" in out
    assert out.count("- ") == 3


def test_headings_code_and_links_survive():
    out = _description_text(_doc(
        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Context"}]},
        _para({"type": "text", "text": "see the spec",
               "marks": [{"type": "link", "attrs": {"href": "https://x/spec"}}]}),
        {"type": "codeBlock", "attrs": {"language": "python"},
         "content": [{"type": "text", "text": "assert row.user_id == user.id"}]},
    ))
    assert "## Context" in out
    assert "[see the spec](https://x/spec)" in out
    assert "```python" in out and "assert row.user_id == user.id" in out


def test_ordered_lists_and_nesting_do_not_collapse():
    out = _description_text(_doc({"type": "orderedList", "content": [
        {"type": "listItem", "content": [_para("First")]},
        {"type": "listItem", "content": [_para("Second")]},
    ]}))
    assert "1. First" in out and "1. Second" in out


def test_hard_breaks_and_mentions_become_text():
    out = _description_text(_doc(_para(
        "ping ",
        {"type": "mention", "attrs": {"text": "@sarah"}},
        {"type": "hardBreak"},
        "after the break",
    )))
    assert "@sarah" in out and "after the break" in out


def test_an_unknown_node_still_yields_its_words():
    """Atlassian adds node types. An unrecognised one must cost formatting, never content —
    silently dropping a paragraph of the specification is the failure that cannot be seen."""
    out = _description_text(_doc({"type": "somethingAtlassianAddedLater", "content": [
        _para("this text still matters"),
    ]}))
    assert "this text still matters" in out


def test_a_plain_string_description_is_accepted():
    """Not every path returns ADF (older sites, some import tooling). Handle both rather than
    returning a stringified dict."""
    assert _description_text("just a string") == "just a string"


def test_empty_and_missing_descriptions_are_empty_strings():
    assert _description_text(None) == ""
    assert _description_text({}) == ""
    assert _description_text(_doc(_para())) == ""


def test_round_trip_through_the_writer_we_already_had():
    """`_adf` is what the platform SENDS to Jira. Reading our own write back must return the
    words we wrote — the outbound path has always carried descriptions; only the inbound one
    threw them away."""
    assert _description_text(_adf("hello from the platform")) == "hello from the platform"


def test_issue_defaults_description_so_an_older_connector_still_constructs():
    assert Issue(key="K-1", summary="s", status="To Do", issue_type="Task",
                 url="u").description == ""


def test_adf_to_text_tolerates_junk():
    for junk in (None, 42, [], {"type": "text"}):
        _adf_to_text(junk)      # must not raise
