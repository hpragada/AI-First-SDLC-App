// Drive the interaction pages and check they behave the way they are meant to.
//
//   npm start                       # in one terminal
//   node tools/verify-journeys.js   # in another
//
// axe reports nothing on any of these pages, so nothing else in this repo can tell whether the
// planted behaviour is actually there. A focus trap that does not trap, or a dialog that happens
// to return focus anyway, would turn into a scoring error the day someone runs an agent over the
// site — the agent would be marked wrong for reporting what the page really does.
//
// Each pair is checked in both directions: the fail page must misbehave AND the pass page must
// behave. A check that only ever asserts the failure would still pass if both pages were broken.

const { chromium } = require("playwright");

const { BASE_URL: BASE } = require("./config");

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? "  OK   " : " WRONG "} ${name}${detail ? "   " + detail : ""}`);
}

// Tab forward and report which element ends up focused, by id.
async function tabTo(page, times) {
  for (let i = 0; i < times; i++) await page.keyboard.press("Tab");
  return page.evaluate(() => document.activeElement.id || document.activeElement.tagName);
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  // ── 2.1.2 keyboard trap ────────────────────────────────────────────
  await page.goto(BASE + "/events/book-a-room");
  await page.click("#room-date-open");
  let escaped = false;
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    const inside = await page.evaluate(() =>
      document.getElementById("room-date-picker").contains(document.activeElement));
    if (!inside) { escaped = true; break; }
  }
  check("/events/book-a-room traps Tab inside the picker", !escaped,
    escaped ? "focus escaped — the trap is not there" : "40 presses, focus never left");
  await page.keyboard.press("Escape");
  const stillOpen = await page.evaluate(() =>
    !document.getElementById("room-date-picker").hidden);
  check("/events/book-a-room ignores Escape", stillOpen);

  await page.goto(BASE + "/events/book-a-seat");
  await page.click("#room-date-open");
  await page.keyboard.press("Escape");
  const seatClosed = await page.evaluate(() => ({
    hidden: document.getElementById("room-date-picker").hidden,
    focused: document.activeElement.id,
  }));
  check("/events/book-a-seat closes on Escape and restores focus",
    seatClosed.hidden && seatClosed.focused === "room-date-open",
    `focus now on #${seatClosed.focused}`);

  // ── 2.4.3 focus return from a dialog ───────────────────────────────
  await page.goto(BASE + "/catalogue/reserve-copy");
  await page.click("#open-reserve");
  await page.click("#cancel-reserve");
  const afterReserve = await page.evaluate(() => document.activeElement.id || document.activeElement.tagName);
  check("/catalogue/reserve-copy drops focus when the dialog closes",
    afterReserve !== "open-reserve", `focus landed on ${afterReserve}`);

  await page.goto(BASE + "/catalogue/place-hold");
  await page.click("#open-reserve");
  await page.click("#cancel-reserve");
  const afterHold = await page.evaluate(() => document.activeElement.id);
  check("/catalogue/place-hold returns focus to the trigger",
    afterHold === "open-reserve", `focus landed on #${afterHold}`);

  // ── 2.4.11 focus obscured by a sticky header ───────────────────────
  // Two things make this awkward to measure, and both are worth knowing before touching it.
  //
  // Direction: moving DOWN a list brings each row to the bottom edge of the viewport, where a
  // header stuck to the top cannot cover it. Rows go behind the header on the way back UP, when
  // the browser aligns their top with the top of the viewport.
  //
  // And it has to be the real keyboard. element.focus() in Chromium centres the element in the
  // viewport, so a row focused that way is never under anything; sequential focus navigation
  // aligns to the nearest edge, which is the behaviour a keyboard user actually gets.
  //
  // Any single step is a poor sample — the browser only scrolls on the steps where the next row
  // is off screen — so walk the whole way back and keep the worst position reached.
  async function highestFocusReached(route) {
    await page.goto(BASE + route);
    for (let i = 0; i < 81; i++) await page.keyboard.press("Tab"); // deep into the list
    let worst = { rowTop: Infinity };
    for (let i = 0; i < 60; i++) {
      await page.keyboard.press("Shift+Tab");
      const here = await page.evaluate(() => {
        const head = document.querySelector(".sticky-head").getBoundingClientRect();
        const row = document.activeElement.getBoundingClientRect();
        return { id: document.activeElement.id, rowTop: Math.round(row.top), headBottom: Math.round(head.bottom) };
      });
      if (here.rowTop < worst.rowTop) worst = here;
    }
    return worst;
  }
  const obscured = await highestFocusReached("/catalogue/all-titles");
  check("/catalogue/all-titles puts a focused row behind the header",
    obscured.rowTop < obscured.headBottom - 1,
    `#${obscured.id} reached top ${obscured.rowTop}, header bottom ${obscured.headBottom}`);
  const clear = await highestFocusReached("/catalogue/by-subject");
  check("/catalogue/by-subject keeps every focused row clear of it",
    clear.rowTop >= clear.headBottom - 1,
    `#${clear.id} stopped at top ${clear.rowTop}, header bottom ${clear.headBottom}`);

  // ── 2.4.3 focus order ──────────────────────────────────────────────
  async function tabOrder(route) {
    await page.goto(BASE + route);
    await page.focus("main form :is(input, select, button)");
    const order = [await page.evaluate(() => document.activeElement.id)];
    for (let i = 0; i < 4; i++) order.push(await tabTo(page, 1));
    const dom = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main form input, main form select, main form button"))
        .map((el) => el.id || el.tagName));
    return { order, dom };
  }
  const scrambled = await tabOrder("/account/settings");
  check("/account/settings tabs in an order the page does not show",
    scrambled.order.join() !== scrambled.dom.join(),
    scrambled.order.join(" → "));
  const natural = await tabOrder("/account/security");
  check("/account/security tabs in the order things appear",
    natural.order.join() === natural.dom.join(),
    natural.order.join(" → "));

  // ── 2.4.7 focus visible ────────────────────────────────────────────
  async function focusStyle(route, selector) {
    await page.goto(BASE + route);
    await page.focus(selector);
    return page.evaluate(() => {
      const s = getComputedStyle(document.activeElement);
      const outline = s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0;
      const shadow = s.boxShadow !== "none" && s.boxShadow !== "";
      return { outline, shadow };
    });
  }
  const noRing = await focusStyle("/help/faq", ".faq-list a");
  check("/help/faq shows nothing when a link is focused",
    !noRing.outline && !noRing.shadow, JSON.stringify(noRing));
  const ring = await focusStyle("/help/contact-us", ".contact-list a");
  check("/help/contact-us shows a ring of its own",
    ring.outline || ring.shadow, JSON.stringify(ring));

  // ── 3.2.1 change of context on focus ────────────────────────
  // Driven with the keyboard, because that is how the failure is met: a value is chosen, focus
  // leaves, and focus comes back. Selecting a value is NOT expected to move on either page —
  // that would be 3.2.2, which is checked below on a different pair.
  async function focusJump(route) {
    await page.goto(BASE + route);
    await page.selectOption("#branch-jump", { index: 3 });
    const afterChange = page.url();
    await page.click("h2");
    await page.focus("#branch-jump");
    await page.waitForTimeout(600);
    return { afterChange, afterFocus: page.url() };
  }

  const jumped = await focusJump("/about/find-a-branch");
  check("/about/find-a-branch leaves the page as soon as the select takes focus",
    jumped.afterChange === BASE + "/about/find-a-branch" &&
      jumped.afterFocus !== BASE + "/about/find-a-branch",
    `on change ${jumped.afterChange.replace(BASE, "")} · on focus ${jumped.afterFocus.replace(BASE, "")}`);

  const stayed = await focusJump("/about/choose-a-branch");
  check("/about/choose-a-branch stays put until Go is pressed",
    stayed.afterFocus === BASE + "/about/choose-a-branch",
    `on focus ${stayed.afterFocus.replace(BASE, "")}`);

  await page.goto(BASE + "/about/choose-a-branch");
  await page.selectOption("#branch-jump", { index: 3 });
  await page.click("#branch-go");
  await page.waitForTimeout(600);
  check("/about/choose-a-branch does move when Go is pressed",
    page.url() !== BASE + "/about/choose-a-branch", page.url().replace(BASE, ""));

  // ── 3.2.2 change of context on input ───────────────────────────────
  // Same wait on both pages: one is expected to have navigated by the end of it, one is not.
  await page.goto(BASE + "/catalogue/filter");
  await page.selectOption("#filter-genre", { index: 2 });
  await page.waitForTimeout(600);
  check("/catalogue/filter navigates the moment the select changes",
    page.url() !== BASE + "/catalogue/filter", page.url().replace(BASE, ""));

  await page.goto(BASE + "/catalogue/refine");
  await page.selectOption("#filter-genre", { index: 2 });
  await page.waitForTimeout(600);
  check("/catalogue/refine waits for the Apply button",
    page.url() === BASE + "/catalogue/refine", page.url().replace(BASE, ""));

  // ── 4.1.3 status messages ──────────────────────────────────────────
  async function announces(route) {
    await page.goto(BASE + route);
    await page.click("#results-search");
    return page.evaluate(() => {
      const el = document.getElementById("results-count");
      return {
        text: el.textContent,
        live: !!el.closest("[aria-live], [role='status'], [role='alert']"),
      };
    });
  }
  const silent = await announces("/catalogue/results");
  check("/catalogue/results injects the count with nothing to announce it",
    silent.text.length > 0 && !silent.live, `"${silent.text}"`);
  const spoken = await announces("/catalogue/quick-find");
  check("/catalogue/quick-find injects the count into a live region",
    spoken.text.length > 0 && spoken.live, `"${spoken.text}"`);

  await browser.close();

  const failed = results.filter((r) => !r.ok).length;
  console.log(failed === 0
    ? `\nall ${results.length} journeys behave as intended`
    : `\n${failed} of ${results.length} journeys do not behave as intended`);
  process.exit(failed === 0 ? 0 : 1);
})();
