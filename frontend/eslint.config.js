import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser } },
    rules: {
      // A raw <a> to an in-app route triggers a FULL PAGE RELOAD, which drops the SPA's state
      // on the way to the destination. `GapReportScreen` carries a comment saying this exact bug
      // was already found and fixed in that one file — it then came back in eight others, which
      // is why it is a rule now and not a code-review habit. Use react-router's <Link to=…>.
      //
      // Core `no-restricted-syntax`, so there is no new dependency. NOTE `npm run lint` is not
      // wired into anything that runs automatically — `make lint` executes ruff and mypy only,
      // despite naming eslint in its comment, and the repo has no CI. The vitest source scan in
      // `src/noRawAnchors.test.ts` is the guard that will actually execute; this one is here to
      // catch it in the editor, where fixing it is cheapest.
      "no-restricted-syntax": [
        "error",
        {
          selector: 'JSXOpeningElement[name.name="a"] > JSXAttribute[name.name="href"] > Literal[value=/^\\x2F/]',
          message: 'Use <Link to="/…"> from react-router-dom — a raw <a> to an in-app route reloads the whole page and loses the SPA\'s state.',
        },
        {
          selector: 'JSXOpeningElement[name.name="a"] > JSXAttribute[name.name="href"] > JSXExpressionContainer > TemplateLiteral[quasis.0.value.raw=/^\\x2F/]',
          message: 'Use <Link to={`/…`}> from react-router-dom — a raw <a> to an in-app route reloads the whole page and loses the SPA\'s state.',
        },
      ],
    },
  },
);
