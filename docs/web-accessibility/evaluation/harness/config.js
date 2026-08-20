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

const path = require("path");

// Override with MERIDIAN_APP when the checkout is somewhere else.
const APP_DIR = process.env.MERIDIAN_APP ||
  path.resolve("C:/Users/Msi/projects/Web-Accessibility/meridian-library-web-accessibility");

const BASE_URL = process.env.MERIDIAN_URL || "http://localhost:4180";

module.exports = {
  APP_DIR,
  BASE_URL,
  appPath: (...parts) => path.join(APP_DIR, ...parts),
  // The recorded axe result lives with the harness, not with the app.
  baselinePath: path.join(__dirname, "axe-baseline.json"),
};
