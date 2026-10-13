PASSES = {
 "1. Sign up, first login and the app shell":
   [1,2,4,5,6,11,12,18,28,29,31,34,171,174,175,255],
 "2. Create a project and fill its profile":
   [3,7,8,9,10,33,211,221,104,259,276],
 "3. Connect your machine":
   [13,14,15,61,84,105,198,206,223],
 "4. People, roles and permissions":
   [19,20,30,46,47,51,52,214,252,225,258,265],
 "5. Integrations":
   [37,38,39,48,74,103,113,156,254],
 "6. Repositories and multi-repo routing":
   [90,91,92,93,94,95,96,97,98,99,100,101,102,106,107,108,109,170,212,277],
 "7. Work items":
   [16,17,21,26,36,40,41,42,43,49,50,54,57,77,118,140,147,167,168,202,117,260,261,
    268,269,279],
 "8. Planning phases, clarifications and the run console":
   [24,25,32,44,53,55,60,62,63,64,65,66,69,71,80,82,83,150,163,172,173,190,191,
    226,227,228,229,231,233,234,251,81,166,184,230,257,262,274,275,280,282],
 "9. Artifacts, traceability and what the agents write":
   [22,23,27,59,67,68,120,121,122,123,124,125,126,131,151,152,165,187,232,253,224,256,264,
    272],
 "10. Gates and approvals":
   [45,56,58,70,189,195,249,250,218,222,263,273],
 "11. Build, code review and merge":
   [72,73,86,87,88,110,111,114,115,116,127,128,129,130,133,134,136,137,139,141,
    144,161,162,199,200,201,203,207,208,239,240,241,243,132,266,267,281],
 "12. Security, testing, CI/CD and deployment phases":
   [176,177,179,180,185,186,193,194,85,178,215,278],
 "13. Failure, recovery and resilience":
   [89,112,135,157,158,160,169,181,182,217,219,220,235,238,242,244,245,246,247,248,183],
 "14. Pushing the backlog to Jira":
   [142,143,236,237],
}

if __name__ == "__main__":
    TRULY_OPEN = {35,75,76,78,79,119,138,148,149,153,154,155,159,164,188,192,196,197,204,205,
                  209,210,213,216,
                  270,271}   # Screen Words groups 1 and 1b - on hold, no code behind them
    SKIP = {145, 146}
    expected = {n for n in range(1, 282) if n not in TRULY_OPEN and n not in SKIP}
    got, dupes = set(), []
    for k, v in PASSES.items():
        for n in v:
            if n in got:
                dupes.append(n)
            got.add(n)
    print("expected %d, assigned %d" % (len(expected), len(got)))
    print("duplicates:", sorted(set(dupes)) or "none")
    print("missing   :", sorted(expected - got) or "none")
    print("extra     :", sorted(got - expected) or "none")
    for k, v in PASSES.items():
        print("  %-58s %d" % (k, len(v)))
