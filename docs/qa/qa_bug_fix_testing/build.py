# -*- coding: utf-8 -*-
"""Build docs/qa/QA_Bug_Fix_Testing.xlsx.

Run it from the repository root:

    .venv/Scripts/python.exe docs/qa/qa_bug_fix_testing/build.py

WHAT THIS IS. The 211 test procedures in the workbook are authored as plain text in the
rows_pass_*.py files beside this one; passes.py says which row belongs to which test
pass. This script assembles them into the workbook - styling, column widths, the Status
dropdown, the three tabs - and refuses to write anything if the content and the pass plan
disagree.

WHY IT IS SAFE TO RE-RUN. Anything a tester has typed - Status, QA Comment, Tested By,
Test Date - is read out of the existing workbook first and written back afterwards, keyed
on S. No. Same idea as read_existing() in docs/qa/build_tracker.py. If the workbook holds
a logged result for a row this build no longer produces, the script REFUSES to write and
names the rows, rather than quietly discarding somebody's work; pass --drop-orphans once
you have decided that losing them is fine.

The Priority and Area columns are read live from docs/Bugs.xlsx, so they cannot drift
away from the register.
"""
import argparse
import datetime
import os
import sys

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import passes             # noqa: E402
import rows_pass_01_04    # noqa: E402
import rows_pass_05_07    # noqa: E402
import rows_pass_08       # noqa: E402
import rows_pass_09_10    # noqa: E402
import rows_pass_11       # noqa: E402
import rows_pass_12_14    # noqa: E402
import rows_batch_2026_09 # noqa: E402
import rows_screen_words_2026_09  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BUGS = os.path.join(REPO, "docs", "Bugs.xlsx")
OUT = os.path.join(REPO, "docs", "qa", "QA_Bug_Fix_Testing.xlsx")

# Columns a tester fills in. Carried forward across a rebuild, keyed on S. No.
QA_COLS = {9: "Status", 10: "QA Comment", 11: "Tested By", 12: "Test Date"}
UNTOUCHED = "Open"          # a Status of exactly this, with nothing else, is not a result

ORANGE = "F26F21"
TYPE_HELP = {
    "DIRECT": "Drive it from the app now.",
    "DURING A RUN": "Watch for it while a phase or build runs.",
    "SET UP FIRST": "Create a condition first, then check.",
    "DEV CHECK": "Not reachable from the app.",
}
COLS = [
    ("S. No", 8, "c"), ("Test Pass", 22, "w"), ("Priority", 9, "c"), ("Area", 24, "w"),
    ("Test Type", 14, "c"), ("The Bug", 62, "w"), ("The Fix", 62, "w"),
    ("How to test it manually live in the app", 78, "w"), ("Status", 11, "c"),
    ("QA Comment", 40, "w"), ("Tested By", 16, "w"), ("Test Date", 13, "c"),
]


def load_content():
    content = {}
    for mod in (rows_pass_01_04, rows_pass_05_07, rows_pass_08,
                rows_pass_09_10, rows_pass_11, rows_pass_12_14, rows_batch_2026_09,
                rows_screen_words_2026_09):
        for sno, row in mod.ROWS.items():
            if sno in content:
                raise SystemExit("two modules both define S.No %s" % sno)
            content[sno] = row
    planned = [n for lst in passes.PASSES.values() for n in lst]
    if len(planned) != len(set(planned)):
        raise SystemExit("a row appears in more than one test pass")
    missing = sorted(set(planned) - set(content))
    extra = sorted(set(content) - set(planned))
    if missing:
        raise SystemExit("no procedure written for: %s" % missing)
    if extra:
        raise SystemExit("procedure written for a row in no pass: %s" % extra)
    return content, planned


def load_meta(planned):
    """Priority and Area, read live from the register so they cannot drift."""
    src = openpyxl.load_workbook(BUGS, data_only=True)["Sheet1"]
    meta = {}
    for r in range(2, src.max_row + 1):
        v = src.cell(r, 1).value
        if v is None:
            continue
        meta[int(str(v).strip())] = (str(src.cell(r, 7).value or "").strip(),
                                     str(src.cell(r, 4).value or "").strip())
    absent = [n for n in planned if n not in meta]
    if absent:
        raise SystemExit("these rows are not in docs/Bugs.xlsx: %s" % absent)

    # There used to be a fallback here for two rows whose Feature cell was empty in the
    # register. The register now carries those values, so the fallback is gone and this
    # complains instead: a blank Area is no use to a tester, and papering over it in the
    # generator would hide the real gap in Bugs.xlsx.
    blank = [n for n in planned if not meta[n][1]]
    if blank:
        raise SystemExit(
            "these rows have an empty Feature cell in docs/Bugs.xlsx: %s\n"
            "  Fill it in there rather than working around it here." % blank)
    return meta


def read_existing():
    """Pull forward everything a tester has typed. Mirrors build_tracker.read_existing."""
    if not os.path.exists(OUT):
        return {}
    book = openpyxl.load_workbook(OUT)
    if "Test cases" not in book.sheetnames:
        return {}
    sheet = book["Test cases"]
    kept = {}
    for r in range(2, sheet.max_row + 1):
        sno = sheet.cell(r, 1).value
        if sno is None:
            continue
        typed = {c: sheet.cell(r, c).value for c in QA_COLS}
        logged = (str(typed[9] or "").strip() not in ("", UNTOUCHED)
                  or any(str(typed[c] or "").strip() for c in (10, 11, 12)))
        if logged:
            kept[int(sno)] = typed
    return kept


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drop-orphans", action="store_true",
                    help="write even though logged results would be lost")
    args = ap.parse_args()

    content, planned = load_content()
    meta = load_meta(planned)
    carried = read_existing()
    # The guide quotes these numbers; derive them so the text cannot drift from the content.
    open_count = len(set(meta) - set(planned) - {145, 146})
    last_sno = max(meta)
    dev = sum(1 for s in planned if content[s][0] == "DEV CHECK")
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    counts = {"<ROWS>": str(len(planned)), "<OPEN>": str(open_count),
              "<DEV>": words.get(dev, str(dev))}

    orphans = sorted(set(carried) - set(planned))
    if orphans and not args.drop_orphans:
        raise SystemExit(
            "REFUSING TO WRITE.\n"
            "  %d row(s) hold a tester's result but are no longer produced by this build:\n"
            "    %s\n"
            "  Rebuilding would discard that work. Put the rows back, or re-run with\n"
            "  --drop-orphans once you have decided losing them is fine."
            % (len(orphans), orphans))

    hdr_fill = PatternFill("solid", fgColor=ORANGE)
    band = PatternFill("solid", fgColor="FDF0E7")
    pass_fill = PatternFill("solid", fgColor="FFF4E5")
    thin = Side(style="thin", color="D9D9D9")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(vertical="top", wrap_text=True)
    ctr = Alignment(vertical="top", horizontal="center", wrap_text=True)
    align = {"w": wrap, "c": ctr}

    wb = openpyxl.Workbook()

    # ---------------------------------------------------------- how to use it
    gu = wb.active
    gu.title = "How to use this sheet"
    gu.sheet_properties.tabColor = ORANGE
    gu.column_dimensions["A"].width = 118
    for i, (kind, text) in enumerate(GUIDE, start=1):
        for token, value in counts.items():
            text = text.replace(token, value)
        c = gu.cell(i, 1)
        if kind == "H":
            c.value, c.font = text, Font(bold=True, size=20, color=ORANGE)
        elif kind == "H2":
            c.value, c.font = text, Font(bold=True, size=13)
        elif kind == "B":
            c.value, c.font = "   •  " + text, Font(size=11)
        elif kind == "P":
            c.value, c.font = text, Font(size=11)
        else:
            c.value = ""
        c.alignment = Alignment(vertical="top", wrap_text=True)

    # ------------------------------------------------------------- test cases
    ws = wb.create_sheet("Test cases")
    for i, (name, width, _) in enumerate(COLS, start=1):
        c = ws.cell(1, i, name)
        c.font = Font(bold=True, color="FFFFFF", size=11)
        c.fill = hdr_fill
        c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        c.border = box
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[1].height = 32

    row, restored = 2, 0
    for n, (pass_name, snos) in enumerate(passes.PASSES.items()):
        shade = (n % 2 == 0)
        for sno in snos:
            shape, bug, fix, how = content[sno]
            pri, area = meta[sno]
            values = [sno, pass_name, pri, area, shape, bug, fix, how, UNTOUCHED, "", "", ""]
            if sno in carried:
                for col, v in carried[sno].items():
                    values[col - 1] = v
                restored += 1
            for i, v in enumerate(values, start=1):
                c = ws.cell(row, i, v)
                c.alignment = align[COLS[i - 1][2]]
                c.border = box
                if shade:
                    c.fill = band
            ws.cell(row, 1).font = Font(bold=True)
            ws.cell(row, 9).font = Font(bold=True)
            ws.cell(row, 2).font = Font(size=10, color="7A4A22")
            ws.cell(row, 5).font = Font(size=10, bold=True)
            row += 1
    last = row - 1

    ws.auto_filter.ref = "A1:L%d" % last
    ws.freeze_panes = "B2"
    dv = DataValidation(type="list",
                        formula1='"Open,Fixed,Failed,Blocked,Not applicable"',
                        allow_blank=False, showDropDown=False)
    dv.errorTitle = "Not a valid status"
    dv.error = "Pick one of: Open, Fixed, Failed, Blocked, Not applicable."
    ws.add_data_validation(dv)
    dv.add("I2:I%d" % last)

    # ---------------------------------------------------------------- summary
    sm = wb.create_sheet("Summary")
    for col, width in zip("ABCDE", (58, 12, 12, 12, 12)):
        sm.column_dimensions[col].width = width

    def hdrow(r, vals):
        for i, v in enumerate(vals, start=1):
            c = sm.cell(r, i, v)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = hdr_fill
            c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
            c.border = box

    sm.cell(1, 1, "Coverage").font = Font(bold=True, size=16, color=ORANGE)
    hdrow(3, ["Test pass", "Rows", "P1", "P2", "P3"])
    r = 4
    for pass_name, snos in passes.PASSES.items():
        ps = [meta[s][0] for s in snos]
        for i, v in enumerate([pass_name, len(snos), ps.count("P1"), ps.count("P2"),
                               ps.count("P3")], start=1):
            c = sm.cell(r, i, v)
            c.border = box
            c.alignment = wrap if i == 1 else ctr
        sm.cell(r, 1).fill = pass_fill
        r += 1
    allp = [meta[s][0] for s in planned]
    for i, v in enumerate(["TOTAL", len(planned), allp.count("P1"), allp.count("P2"),
                           allp.count("P3")], start=1):
        c = sm.cell(r, i, v)
        c.font = Font(bold=True)
        c.border = box
        c.alignment = wrap if i == 1 else ctr

    r += 3
    sm.cell(r, 1, "By test type").font = Font(bold=True, size=13)
    r += 1
    hdrow(r, ["Test type", "Rows", "", "", ""])
    r += 1
    for t in ("DIRECT", "DURING A RUN", "SET UP FIRST", "DEV CHECK"):
        c = sm.cell(r, 1, "%s - %s" % (t, TYPE_HELP[t]))
        c.border, c.alignment = box, wrap
        c = sm.cell(r, 2, sum(1 for s in planned if content[s][0] == t))
        c.border, c.alignment = box, ctr
        r += 1

    r += 2
    sm.cell(r, 1, "Not in this sheet").font = Font(bold=True, size=13)
    r += 1
    for line in [
        "%d rows are genuinely open with no code written yet - they stay Open in Bugs.xlsx." % open_count,
        "S. No 145 is a numbered row in Bugs.xlsx with every other cell blank.",
        "S. No 146 is superseded by S. No 240, which IS in this sheet.",
        "Built %s against docs/Bugs.xlsx as at S. No %d."
        % (datetime.date.today().isoformat(), last_sno),
        "Rebuild: .venv/Scripts/python.exe docs/qa/qa_bug_fix_testing/build.py",
    ]:
        c = sm.cell(r, 1, line)
        c.alignment = wrap
        r += 1

    wb.save(OUT)
    print("wrote %s" % os.path.relpath(OUT, REPO))
    print("  %d rows across %d test passes" % (last - 1, len(passes.PASSES)))
    print("  %d tester result(s) carried forward" % restored)


GUIDE = [
    ("H", "QA_Bug_Fix_Testing"),
    ("P", "Every fix made to the SDLC platform that has been written in code but has NOT yet been "
          "confirmed by a QA member using the app on a real tenant account. <ROWS> rows."),
    ("", ""),
    ("H2", "What is in here, and what is not"),
    ("P", "IN: every P1, P2 and P3 row of docs/Bugs.xlsx whose fix exists in the code - whether the "
          "row currently reads Fixed or Open. Rows already marked Fixed are included because almost "
          "none of them was ever signed off by your side; they were verified by tests, or by a "
          "browser pass done by the developer, which is not the same thing."),
    ("P", "OUT: <OPEN> rows that are genuinely open with no code behind them yet, plus one numbered row "
          "with no content and one row superseded by another. Those stay Open in Bugs.xlsx and are "
          "nothing to do with this pass."),
    ("", ""),
    ("H2", "How to work through it"),
    ("P", "Work down the TEST PASS column in order, 1 to 14. The passes follow the real journey "
          "through the product, so a single run through the lifecycle will let you tick off dozens "
          "of rows at once. Testing in S. No order instead would make you set up the same "
          "conditions over and over."),
    ("", ""),
    ("H2", "The Test Type column - read this before you start"),
    ("P", "Not every fix is a button you can click. Each row says honestly which kind it is:"),
    ("B", "DIRECT - you can drive it from the app right now. Most rows are this."),
    ("B", "DURING A RUN - there is no isolated test; the check happens at a particular moment while "
          "a phase or a build is running. The steps say where in the journey to look."),
    ("B", "SET UP FIRST - you have to create a condition before you can see it: stop the app, "
          "restart the worker, delete a Jira issue, sign in as somebody without a role. The steps "
          "say exactly how."),
    ("B", "DEV CHECK - genuinely not reachable from the app. There are only <DEV> of these. Mark them "
          "'Not applicable' unless the team asks otherwise; they are listed so the sheet accounts "
          "for every row rather than quietly skipping one."),
    ("", ""),
    ("H2", "Filling it in"),
    ("P", "Status starts as Open on every row. Change it to Fixed when you have confirmed it live, "
          "and please always write something in QA Comment - what you saw, or what you could not "
          "set up. A row marked Fixed with no comment tells the next person nothing."),
    ("B", "Fixed - you tested it and it works."),
    ("B", "Failed - you tested it and it does not. Put the exact wording or behaviour you saw in "
          "the comment; that detail is what makes it fixable."),
    ("B", "Blocked - you could not test it (no Jira account, no second machine, no way to create "
          "the condition). Say what you were missing."),
    ("B", "Not applicable - the row cannot be tested from the app at all."),
    ("P", "Your entries survive a rebuild of this sheet - the generator reads them back out and "
          "writes them in again, keyed on S. No. You do not need to keep a private copy."),
    ("", ""),
    ("H2", "Two things worth knowing before you begin"),
    ("P", "Start with S. No 245 in Pass 13. It is the check that the worker starts at all. If that "
          "one fails, nothing else in this sheet can be tested."),
    ("P", "Some steps are destructive and cannot be undone - cancelling a work item (S. No 140), "
          "and deleting Jira issues (S. No 236). Use throwaway items and a throwaway Jira project "
          "for those."),
    ("", ""),
    ("H2", "Environment"),
    ("P", "Getting a machine set up is covered in docs/AI-First-SDLC-Platform-QA-Testing-Guide.pdf "
          "and is not repeated here. Each row lists only its own preconditions."),
    ("P", "Several passes need things that may not be available to everyone: a connected companion "
          "machine, a GitHub repository with a token, a Jira or Confluence account, a second user "
          "account, and for a few rows a second machine. If you do not have one, mark those rows "
          "Blocked and say which piece was missing rather than guessing at a result."),
    ("", ""),
    ("H2", "When you are done"),
    ("P", "Hand the sheet back to the team. Because the S. No column is the original Bugs.xlsx "
          "number, your results map straight back onto the bug sheet with no translation."),
]


if __name__ == "__main__":
    main()
