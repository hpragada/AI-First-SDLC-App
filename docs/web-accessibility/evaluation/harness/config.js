// Where the fixture app lives, and where to reach it while it is running.
//
// This harness used to sit inside the Meridian Library repository, next to the app it checks.
// It was moved out because that repository gets onboarded as a brownfield project, and code
// intelligence indexes what it finds there: `builtin.py` treats `.js` as source and `.json` as
// context, and `codeintel_mcp.py` mines commit messages for "decision archaeology". Every file
// in this folder names a route, a criterion and the verdict expected of it — together they are
// the answer key. Indexed alongside the app, they would let an agent "find" the planted defects
// by reading the tests rather than by examining the pages, and the whole measurement would be
// worth nothing.
//
// So the rule is simple: the app repository holds only what a real library application would
// hold. Anything that knows what the answers are lives here.

const fs = require("fs");
const path = require("path");

// Where the app checkout is. `MERIDIAN_APP` wins; otherwise look for it beside this
// repository, which is where it sits for anyone who cloned the two side by side.
//
// This used to fall back to one developer's absolute path. That is not a small thing: every
// script here reads the app directory, so on any other machine all eight checks died on the
// first file read, and the fix was an environment variable nobody had been told about. A
// default that only works for the person who wrote it is a default that hides the tool.
const SIBLING = path.resolve(__dirname, "..", "..", "..", "..", "..",
  "meridian-library-web-accessibility");
const APP_DIR = process.env.MERIDIAN_APP || SIBLING;

if (!fs.existsSync(path.join(APP_DIR, "routes.json"))) {
  console.error(
    `Cannot find the Meridian app.
` +
    `  looked in: ${APP_DIR}
` +
    `  Set MERIDIAN_APP to the checkout, e.g.
` +
    `      MERIDIAN_APP=/path/to/meridian-library-web-accessibility npm run check
` +
    `  (routes.json is what is missing, so this is the wrong directory rather than a broken one.)`
  );
  process.exit(1);
}

const BASE_URL = process.env.MERIDIAN_URL || "http://localhost:4180";

module.exports = {
  APP_DIR,
  BASE_URL,
  appPath: (...parts) => path.join(APP_DIR, ...parts),
  // The recorded axe result lives with the harness, not with the app.
  baselinePath: path.join(__dirname, "axe-baseline.json"),
};
