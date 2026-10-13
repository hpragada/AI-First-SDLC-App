import { forwardRef, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type {
  ButtonHTMLAttributes,
  CSSProperties,
  HTMLAttributes,
  InputHTMLAttributes,
  LabelHTMLAttributes,
  ReactNode,
  RefObject,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { Link as RouterLink } from "react-router-dom";

import { failureOf } from "../../api";

// Which overlays are open, innermost last. Every `useEscapeToClose` listens on `window`, so
// without this they ALL fired on one Escape: opening the type tooltip inside the New work item
// drawer and pressing Escape shut the tooltip *and* the drawer, throwing away whatever the person
// had typed. One press dismisses one layer — the top one — which is what a reader expects and
// what WCAG 2.2 §1.4.13 means by a tooltip being "dismissible": the tooltip goes, not the page
// behind it. Found in the live pass, 2026-09-30.
const escapeStack: number[] = [];
let nextEscapeId = 1;

// Close an overlay on the Esc key. No-op when there's no handler (e.g. inline gallery swatches).
function useEscapeToClose(onClose?: () => void) {
  const idRef = useRef(0);
  if (idRef.current === 0) idRef.current = nextEscapeId++;
  const active = Boolean(onClose);

  // Registration is keyed on `active` ALONE, deliberately. Keying it on `onClose` would re-push
  // this overlay to the top of the stack every time its parent re-rendered with a fresh arrow
  // function — so a drawer would silently steal the top slot from the tooltip open inside it.
  useEffect(() => {
    if (!active) return;
    const id = idRef.current;
    escapeStack.push(id);
    return () => {
      const at = escapeStack.indexOf(id);
      if (at !== -1) escapeStack.splice(at, 1);
    };
  }, [active]);

  useEffect(() => {
    if (!onClose) return;
    const handle = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      // Who is on top is decided ONCE per keypress, by whichever of these listeners sees the
      // event first, and every later one reads that answer rather than the live stack. Belt and
      // braces alongside the capture phase below: between them, no amount of closing and
      // unmounting part-way through a single keypress can change the answer half-way.
      const claim = event as KeyboardEvent & { __escapeClaimedBy?: number };
      if (claim.__escapeClaimedBy === undefined) {
        claim.__escapeClaimedBy = escapeStack[escapeStack.length - 1] ?? -1;
      }
      if (claim.__escapeClaimedBy !== idRef.current) return;
      onClose();
    };
    // CAPTURE phase, and that is the half of this that actually does the work.
    //
    // `useDismissable` binds its own Escape handler to `document`, in the bubble phase. React
    // flushes the close it triggers synchronously, so by the time any bubble-phase `window`
    // listener runs, the inner overlay has already been taken off the stack AND its own listener
    // unbound — leaving the outer one as the only handler still standing, reading a stack that no
    // longer mentions the layer that was above it, and closing on a keypress that was not for it.
    // Capture runs before all of that, while the stack still describes what is on screen.
    //
    // Worth knowing if this is ever revisited: jsdom flushes differently, so the bubble-phase
    // version passed its unit test and still shut the drawer in a real browser. The test below it
    // is honest only because the behaviour was also checked in one.
    window.addEventListener("keydown", handle, true);
    return () => window.removeEventListener("keydown", handle, true);
  }, [onClose]);
}

/** Dismiss a popover on an outside click or Escape, and move focus into it when it opens.
 *
 * Extracted from the topbar account menu when the work-items board grew a row menu of its own
 * (Bugs S.No 140). The markup of the two differs; this — the part that is easy to get subtly
 * wrong, and the part a keyboard user notices when it is — does not, so it is written once.
 * `firstItem` is focused on open so a menu opened from the keyboard does not strand you at the
 * trigger with no way in.
 */
export function useDismissable(
  open: boolean,
  onClose: () => void,
  root: RefObject<HTMLElement | null>,
  firstItem?: RefObject<HTMLElement | null>,
  // The popup itself, when it is drawn in the floating layer rather than inside `root` (Bugs
  // S.No 166). A popup moved to the top of the page is no longer inside its trigger's element, so
  // "was the click inside `root`?" would answer NO for a click on the popup's own items — and the
  // menu would close under the pointer that was choosing from it. Callers that keep their popup
  // inside `root` pass nothing and behave exactly as before.
  popup?: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (root.current?.contains(target) || popup?.current?.contains(target)) return;
      onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose, root, popup]);

  useEffect(() => {
    if (open) firstItem?.current?.focus();
  }, [open, firstItem]);
}

/** Draws its children at the top of the page, outside every panel that could clip them.
 *
 * **Why popups float (Bugs S.No 166).** A panel hides whatever crosses its edge
 * (`.panel { overflow: hidden }`, which is what keeps its rounded corners clean). A dropdown drawn
 * inside one was cut off where it crossed that edge — and because a long list grows its own
 * scrollbar, it was the SHORT lists that broke: six items, too few to scroll, enough to cross the
 * edge. The same held for the row menu on the Work Items list. Moving every popup here removes
 * the whole class rather than the two instances somebody noticed.
 *
 * Pair it with `useFloatingPosition` (a popup up here no longer knows where its trigger is) and
 * give the popup the `popover-layer` class.
 */
export function FloatingLayer({ children }: { children: ReactNode }) {
  return createPortal(children, document.body);
}

/** Puts a floating popup beside its trigger, and keeps it there while the page moves.
 *
 * Below the trigger by default; **above it when it does not fit below and there is more room
 * above** — the team's choice (flip upwards, rather than shrink into a small scrolling box). It
 * scrolls only when it fits neither way. `preferAbove` reverses the preference, for a tooltip.
 *
 * Re-measured on every render, on any scroll — capture phase, so a scrolling panel counts as well
 * as the window — and on resize: a popup placed once is stranded mid-screen the moment anything
 * under it moves.
 *
 * Writes straight to the popup's style instead of going through React state. Measuring in a
 * layout effect and then setting state re-renders, which measures again.
 */
export function useFloatingPosition(
  open: boolean,
  anchor: RefObject<HTMLElement | null>,
  floating: RefObject<HTMLElement | null>,
  { align = "start", matchWidth = false, preferAbove = false, gap = 4, overlay = false }: {
    /** Which edge of the trigger the popup lines up with: menus hang from the right. */
    align?: "start" | "end" | "center";
    /** Same width as the trigger — a dropdown list under its field. */
    matchWidth?: boolean;
    preferAbove?: boolean;
    gap?: number;
    /**
     * Draw the popup OVER the trigger rather than beside it, growing rightwards and downwards
     * from the trigger's own corner and never narrower than it.
     *
     * This is how a cut-off row shows the rest of its text: the row appears to open out where it
     * already is, so the eye does not have to travel and the list underneath does not reflow.
     * `align`, `gap` and `preferAbove` do not apply — the trigger's top-left IS the position,
     * clamped so the popup stays on screen.
     */
    overlay?: boolean;
  } = {},
) {
  const place = useCallback(() => {
    const trigger = anchor.current;
    const popup = floating.current;
    if (!trigger || !popup) return;
    const box = trigger.getBoundingClientRect();
    const margin = 8;
    if (overlay) {
      popup.style.minWidth = `${box.width}px`;
      const width = popup.offsetWidth;
      const height = popup.offsetHeight;
      const room = (space: number, size: number) => Math.max(margin, space - size - margin);
      popup.style.top =
        `${Math.min(Math.max(box.top, margin), room(window.innerHeight, height))}px`;
      popup.style.left =
        `${Math.min(Math.max(box.left, margin), room(window.innerWidth, width))}px`;
      return;
    }
    if (matchWidth) popup.style.width = `${box.width}px`;
    popup.style.maxHeight = "";               // measure at its natural (CSS-capped) height
    const height = popup.offsetHeight;
    const width = popup.offsetWidth;
    const below = window.innerHeight - box.bottom - gap - margin;
    const above = box.top - gap - margin;
    const up = preferAbove
      ? height <= above || above >= below
      : height > below && above > below;
    const room = Math.max(up ? above : below, 0);
    if (height > room) popup.style.maxHeight = `${room}px`;
    const shown = Math.min(height, room);
    popup.style.top = `${up ? box.top - gap - shown : box.bottom + gap}px`;
    const wanted =
      align === "end" ? box.right - width
        : align === "center" ? box.left + box.width / 2 - width / 2
          : box.left;
    const furthest = Math.max(margin, window.innerWidth - width - margin);
    popup.style.left = `${Math.min(Math.max(wanted, margin), furthest)}px`;
    popup.dataset.side = up ? "above" : "below";
  }, [anchor, floating, align, matchWidth, preferAbove, gap, overlay]);

  useLayoutEffect(() => {
    if (open) place();
  });

  useEffect(() => {
    if (!open) return;
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, place]);
}

/** Tab from inside a floating menu.
 *
 * A menu drawn in the floating layer sits at the END of the page, so the browser's Tab from inside
 * it would carry focus off the page instead of to whatever follows the trigger. Handing focus back
 * to the trigger first — and letting the browser's own Tab carry on from there — lands it exactly
 * where it went when the menu was drawn inline. */
export function closeOnTab(close: () => void, trigger: RefObject<HTMLElement | null>) {
  return (event: React.KeyboardEvent) => {
    if (event.key !== "Tab") return;
    trigger.current?.focus();
    close();
  };
}

/** True when an element is showing less text than it holds — i.e. the CSS cut it off. */
export function isCut(el: HTMLElement | null | undefined): boolean {
  return !!el && el.scrollWidth > el.clientWidth + 1;
}

/** Shows a cut-off label in full, drawn over the thing that cut it.
 *
 * A dropdown row is one line as wide as its field, so a long label is cut with an ellipsis and
 * the rest is simply unreachable — no hover, no wrap. That is fine for the platform's own short
 * choices and wrong for work items, whose titles agents write from findings: they are long, and
 * the words that tell two of them apart are at the END ("ExpenseResponse missing created_at" vs
 * "ExpenseResponse missing currency"). Picking the wrong one starts a phase run on the wrong work
 * item.
 *
 * It opens only when the label is ACTUALLY cut, so short labels behave exactly as before, and it
 * follows the arrow keys as well as the pointer — a keyboard user cannot hover. `aria-hidden`
 * because nothing here is new to a screen reader: the full text is already the row's accessible
 * name, only visually clipped, so announcing it again would just repeat it.
 */
function TruncationPeek({ text, element }: { text: string; element: HTMLElement | null }) {
  // A plain box holding the current anchor, written during render: `useFloatingPosition` reads it
  // in a layout effect, after this render has committed.
  const anchor = useRef<HTMLElement | null>(null);
  anchor.current = element;
  const peek = useRef<HTMLDivElement>(null);
  const open = Boolean(element && text);
  useFloatingPosition(open, anchor, peek, { overlay: true });
  if (!open) return null;
  return (
    <FloatingLayer>
      <div ref={peek} className="popover-layer peek" aria-hidden="true">
        {text}
      </div>
    </FloatingLayer>
  );
}

export type RowMenuItem =
  | { label: ReactNode; href: string; danger?: boolean }
  | { label: ReactNode; onSelect: () => void; danger?: boolean };

/** The "⋯" menu at the end of a table row.
 *
 * A menu rather than the buttons laid out in the cell: a row is already dense, and an action
 * that removes work from a board should take a deliberate second click rather than sit under
 * the cursor of someone scanning a list. `label` names WHICH row it belongs to — "Actions"
 * repeated forty times tells a screen-reader user nothing about where they are.
 */
export function RowMenu({ label, items }: { label: string; items: RowMenuItem[] }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const first = useRef<HTMLAnchorElement | HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismissable(open, close, root, first, pop);
  // Floating, not inline (S.No 166): this menu lives in the last cell of a table inside a panel,
  // and the panel clipped it — the same defect as the work-item picker, unnoticed only because
  // this menu holds two short items.
  useFloatingPosition(open, trigger, pop, { align: "end" });

  if (items.length === 0) return null;
  return (
    <div className="row-menu" ref={root}>
      <button
        ref={trigger}
        type="button"
        className="row-menu__trigger"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        {/* Three full stops, not the single "…" character: this is a control, and the ellipsis
            glyph is read aloud as "dot dot dot" by some screen readers mid-sentence. The
            aria-label above is what is actually announced; this is decorative. */}
        <span aria-hidden="true">...</span>
      </button>
      {open && (
        <FloatingLayer>
        <div
          ref={pop}
          className="popover-layer row-menu__pop"
          role="menu"
          aria-label={label}
          onKeyDown={closeOnTab(close, trigger)}
        >
          {items.map((item, index) => {
            const ref = index === 0 ? first : undefined;
            const className = cx("row-menu__item", item.danger && "row-menu__item--danger");
            return "href" in item ? (
              <RouterLink
                key={index}
                ref={ref as RefObject<HTMLAnchorElement>}
                className={className}
                role="menuitem"
                to={item.href}
                onClick={close}
              >
                {item.label}
              </RouterLink>
            ) : (
              <button
                key={index}
                ref={ref as RefObject<HTMLButtonElement>}
                type="button"
                className={className}
                role="menuitem"
                onClick={() => { close(); item.onSelect(); }}
              >
                {item.label}
              </button>
            );
          })}
        </div>
        </FloatingLayer>
      )}
    </div>
  );
}

export type FilterChoice = { value: string; label: string; count: number };

/**
 * A filter dropdown that shows how many items each choice would return, right-aligned
 * (Work Items, 2026-10-08). The browser's own <select> can only draw one line of plain text per
 * option, so the counts came out as "Architecture (0)" — the team's approved mockup has them in a
 * column of their own, and this is what draws that.
 *
 * A choice with nothing behind it is greyed but still selectable: picking it shows an honest
 * empty board. Keyboard: Enter / Space / ↓ open; ↑ ↓ Home End move; Enter or Space picks; Esc
 * and Tab close, focus returning to the box. Listbox ARIA, so a screen reader announces each
 * choice with its count and which one is selected.
 */
export function FilterSelect({
  label, prefix, allLabel, allCount, options, value, onChange,
}: {
  /** Accessible name, e.g. "Filter by phase". */
  label: string;
  /** Shown in the closed box before the choice: "Phase" → "Phase: Ideation". */
  prefix: string;
  /** The first row of the list, e.g. "All phases". */
  allLabel: string;
  allCount: number;
  options: FilterChoice[];
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rows: FilterChoice[] = [{ value: "", label: allLabel, count: allCount }, ...options];
  const selectedIndex = Math.max(0, rows.findIndex((r) => r.value === value));
  const [active, setActive] = useState(selectedIndex);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const close = useCallback(() => {
    setOpen(false);
    trigger.current?.focus();
  }, []);
  useDismissable(open, close, root, list, list);
  useFloatingPosition(open, trigger, list, { align: "start" });

  const show = () => {
    setActive(selectedIndex);
    setOpen(true);
  };
  const pick = (index: number) => {
    onChange(rows[index].value);
    close();
  };
  const selected = rows[selectedIndex];

  const onTriggerKey = (event: React.KeyboardEvent) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
      event.preventDefault();
      show();
    }
  };
  const onListKey = (event: React.KeyboardEvent) => {
    const last = rows.length - 1;
    const move: Record<string, number> = {
      ArrowDown: Math.min(last, active + 1), ArrowUp: Math.max(0, active - 1), Home: 0, End: last,
    };
    if (event.key in move) {
      event.preventDefault();
      setActive(move[event.key]);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      pick(active);
    } else if (event.key === "Tab") {
      close();
    }
  };

  return (
    <div className="filter-select" ref={root}>
      <button
        ref={trigger}
        type="button"
        className="select select--fit filter-select__box"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? `${id}-list` : undefined}
        onClick={() => (open ? close() : show())}
        onKeyDown={onTriggerKey}
      >
        <span>{prefix}: {selected.value === "" ? "All" : selected.label}</span>
        <span className="filter-select__count">{selected.count}</span>
      </button>
      {open && (
        <FloatingLayer>
          <ul
            ref={list}
            id={`${id}-list`}
            className="popover-layer filter-select__list"
            role="listbox"
            aria-label={label}
            tabIndex={-1}
            aria-activedescendant={`${id}-${active}`}
            onKeyDown={onListKey}
          >
            {rows.map((row, index) => (
              <li
                key={row.value || "all"}
                id={`${id}-${index}`}
                role="option"
                aria-selected={index === selectedIndex}
                className={cx(
                  "filter-select__option",
                  index === active && "is-active",
                  index === selectedIndex && "is-selected",
                  row.count === 0 && "is-empty",
                )}
                onMouseEnter={() => setActive(index)}
                onClick={() => pick(index)}
              >
                <span>{row.label}</span>
                <span className="filter-select__count">{row.count}</span>
              </li>
            ))}
          </ul>
        </FloatingLayer>
      )}
    </div>
  );
}

type Variant =
  | "primary"
  | "secondary"
  | "ghost"
  | "danger"
  | "danger-solid";
// Exported so a caller can hold a variant in a lookup table rather than a chain of ternaries —
// the artifact registry maps five artifact statuses to badges this way.
export type BadgeVariant =
  | "queued"
  | "neutral"
  | "waiting"
  | "running"
  | "needs-answer"
  | "gate"
  | "done"
  | "failed"
  | "parked"
  | "info-hue"
  | "navy"
  | "orange"
  | "outline"
  // Bugs S.No 140. Deliberately NOT "done" and deliberately NOT "failed": abandoned work
  // neither succeeded nor broke, and borrowing either colour would say something untrue at a
  // glance. Muted, so a cancelled row recedes on a board without disappearing from it.
  | "cancelled"
  // Bugs S.No 246. "Waiting on a machine that isn't there", as against `gate`'s "waiting on a
  // person" — same amber, separate name, because only one of the two is a fault to fix.
  | "paused";
type BannerVariant = "info" | "warning" | "danger" | "success" | "purple";

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function Button({
  variant = "secondary",
  size,
  block,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm";
  block?: boolean;
}) {
  return (
    <button
      className={cx(
        "btn",
        `btn--${variant}`,
        size === "sm" && "btn--sm",
        block && "btn--block",
        className,
      )}
      {...props}
    />
  );
}

export function Field({
  label,
  help,
  error,
  required,
  children,
  className,
  style,
}: LabelHTMLAttributes<HTMLLabelElement> & {
  label: ReactNode;
  help?: ReactNode;
  error?: ReactNode;
  required?: boolean;
}) {
  return (
    <label className={cx("field", Boolean(error) && "field--error", className)} style={style}>
      <span className="field__label">
        {label}
        {required && <span className="req">*</span>}
      </span>
      {children}
      {help && <span className="field__help">{help}</span>}
      {error && <span className="field__error">{error}</span>}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx("input", props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx("select", props.className)} />;
}

/** Forwards its ref, so a screen that refuses a save can put the cursor in the field it is
 *  asking about (the project profile's description). */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea(props, ref) {
    return <textarea {...props} ref={ref} className={cx("textarea", props.className)} />;
  },
);

export type ComboboxOption = { value: string; label: string };

/**
 * A Select you can type to search (Bugs S.No 150). A plain <select> over a long list (e.g. every
 * work item in a project) forces the user to scroll and eyeball dozens of entries; here the
 * filtering happens in the dropdown itself.
 *
 * Keyboard: ↑/↓ move, Enter picks, Esc closes/reverts. Uses the standard combobox ARIA roles so
 * screen readers announce it, and reuses the `.input` styling so it matches every other control.
 */
export function Combobox({
  options,
  value,
  onChange,
  placeholder,
  disabled,
  emptyText = "No matches",
  id,
}: {
  options: ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  emptyText?: string;
  id?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const selected = options.find((o) => o.value === value) ?? null;
  // The row (or the closed field) whose full text is being shown, and that text.
  const [peekEl, setPeekEl] = useState<HTMLElement | null>(null);
  const [peekText, setPeekText] = useState("");
  const rowEls = useRef(new Map<number, HTMLLIElement>());
  const hidePeek = () => setPeekEl(null);
  const peekAt = (el: HTMLElement | null | undefined, text: string) => {
    if (el && isCut(el)) {
      setPeekEl(el);
      setPeekText(text);
    } else {
      setPeekEl(null);
    }
  };

  // While closed the box shows the current selection; typing filters the list.
  const text = open ? query : selected?.label ?? "";
  const matches = open
    ? options.filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase()))
    : options;

  // The shared hook, not a private copy of it (S.No 166). This component had its own outside-click
  // effect — "was the click inside me?" — which is exactly the check that inverts once the list is
  // drawn in the floating layer. One behaviour for every popup, fixed in one place.
  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setPeekEl(null);
  }, []);
  useDismissable(open, close, rootRef, undefined, listRef);
  useFloatingPosition(open, inputRef, listRef, { matchWidth: true });

  const pick = (option: ComboboxOption) => {
    onChange(option.value);
    setOpen(false);
    setQuery("");
    setPeekEl(null);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        setQuery("");
        return;
      }
      const step = e.key === "ArrowDown" ? 1 : -1;
      const next = matches.length ? (active + step + matches.length) % matches.length : 0;
      setActive(next);
      // The highlight is the keyboard's pointer, so the full title follows it the same way it
      // follows the mouse. The row is already on the page, so it can be measured now.
      peekAt(rowEls.current.get(next), matches[next]?.label ?? "");
    } else if (e.key === "Enter") {
      if (open && matches[active]) {
        e.preventDefault();
        pick(matches[active]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
      setPeekEl(null);
    }
  };

  return (
    <div className="combobox" ref={rootRef}>
      <input
        ref={inputRef}
        id={id}
        className="input combobox__input"
        role="combobox"
        aria-expanded={open}
        aria-controls={id ? `${id}-listbox` : undefined}
        aria-autocomplete="list"
        autoComplete="off"
        disabled={disabled}
        placeholder={placeholder}
        value={text}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
          setOpen(true);
          setPeekEl(null);        // the rows under it have just changed
        }}
        onFocus={() => {
          setOpen(true);
          setQuery("");
          setPeekEl(null);
        }}
        // A pick leaves focus in the field, so opening on focus alone meant a second click on the
        // field did nothing — you had to click away and back (found live, 2026-09-21). A click
        // anywhere on the field opens it.
        onClick={() => {
          if (!open) {
            setOpen(true);
            setQuery("");
            setPeekEl(null);
          }
        }}
        // Closed and showing a chosen title too long for the field: hovering the field shows it
        // in full, the same way a row does.
        onMouseEnter={(e) => {
          if (!open && selected) peekAt(e.currentTarget, selected.label);
        }}
        onMouseLeave={hidePeek}
        onKeyDown={onKeyDown}
      />
      {open && (
        <FloatingLayer>
          <ul
            ref={listRef}
            className="popover-layer combobox__list"
            role="listbox"
            id={id ? `${id}-listbox` : undefined}
            onMouseLeave={hidePeek}
          >
            {matches.length === 0 ? (
              <li className="combobox__empty">{emptyText}</li>
            ) : (
              matches.map((o, i) => (
                <li
                  key={o.value}
                  role="option"
                  aria-selected={o.value === value}
                  ref={(el) => {
                    if (el) rowEls.current.set(i, el);
                    else rowEls.current.delete(i);
                  }}
                  className={cx(
                    "combobox__option",
                    i === active && "combobox__option--active",
                    o.value === value && "combobox__option--selected",
                  )}
                  onMouseEnter={(e) => {
                    setActive(i);
                    peekAt(e.currentTarget, o.label);
                  }}
                  // mousedown (not click): the input's blur would close the list first.
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pick(o);
                  }}
                >
                  {o.label}
                </li>
              ))
            )}
          </ul>
        </FloatingLayer>
      )}
      {/* Outside the list, because the closed field can be cut off too. */}
      <TruncationPeek text={peekText} element={peekEl} />
    </div>
  );
}

/** A dropdown the platform draws itself, for choices too long for the browser's own (Bugs
 * S.No 184).
 *
 * The browser's `<select>` is drawn by the operating system, outside the page: nothing in the app
 * can keep it inside its card or make an option wrap. Agents routinely write options that are
 * whole sentences, so on the clarification screen they ran on one unbroken line off the card.
 * This list is as wide as its field and wraps.
 *
 * Reach for it only where the options can be long and are written by an agent. Where they are
 * short and the platform's own, keep `Select` — the browser's control is the better control.
 *
 * Everything a native select gives for free is rebuilt on purpose, because this is an
 * accessibility product: a real button, so Tab reaches it and Enter or Space opens it; ↑ ↓ Home End
 * move; Enter or Space picks; Escape closes and changes nothing. It follows the select-only
 * combobox pattern — `role="combobox"` on the button, the highlighted option named by
 * `aria-activedescendant` — so a screen reader announces a list of choices and the one under the
 * highlight while focus stays on the control.
 */
export function ChoiceSelect({
  options,
  value,
  onChange,
  placeholder = "Choose one…",
  invalid,
  disabled,
  id,
}: {
  options: ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  invalid?: boolean;
  disabled?: boolean;
  id?: string;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const autoId = useId();
  const listId = `${id ?? autoId}-listbox`;
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  // Set when a key picked an option, so the click some browsers still send for that same key press
  // cannot reopen the list it just closed. Cleared straight after the key is released.
  const keyPicked = useRef(false);
  const selectedIndex = options.findIndex((o) => o.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : null;
  const close = useCallback(() => setOpen(false), []);
  useDismissable(open, close, rootRef, undefined, listRef);
  useFloatingPosition(open, buttonRef, listRef, { matchWidth: true });

  // Keep the highlighted option in view as the arrow keys walk a list longer than the popup.
  useEffect(() => {
    if (open) document.getElementById(`${listId}-${active}`)?.scrollIntoView?.({ block: "nearest" });
  }, [open, active, listId]);

  const openList = () => {
    setActive(selectedIndex >= 0 ? selectedIndex : 0);
    setOpen(true);
  };
  const pick = (index: number) => {
    const option = options[index];
    if (option) onChange(option.value);
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!open) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        openList();
      }
      // Enter and Space are left to the button's own activation, which arrives as a click.
      return;
    }
    const last = options.length - 1;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((i) => Math.min(i + 1, last));
        break;
      case "ArrowUp":
        event.preventDefault();
        setActive((i) => Math.max(i - 1, 0));
        break;
      case "Home":
        event.preventDefault();
        setActive(0);
        break;
      case "End":
        event.preventDefault();
        setActive(last);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        keyPicked.current = true;
        pick(active);
        break;
      case "Escape":
        event.preventDefault();
        close();
        break;
      case "Tab":
        close();
        break;
    }
  };

  return (
    <div className="choice-select" ref={rootRef}>
      <button
        ref={buttonRef}
        id={id}
        type="button"
        className={cx("select", "choice-select__button", !selected && "choice-select__button--empty")}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open && options.length > 0 ? `${listId}-${active}` : undefined}
        aria-invalid={invalid || undefined}
        disabled={disabled}
        onClick={() => {
          if (keyPicked.current) return;
          if (open) close();
          else openList();
        }}
        onKeyDown={onKeyDown}
        onKeyUp={() => {
          window.setTimeout(() => {
            keyPicked.current = false;
          }, 0);
        }}
      >
        {selected ? selected.label : placeholder}
      </button>
      {open && (
        <FloatingLayer>
          <ul ref={listRef} id={listId} role="listbox" className="popover-layer choice-select__list">
            {options.map((o, i) => (
              <li
                key={o.value}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={o.value === value}
                className={cx(
                  "choice-select__option",
                  i === active && "choice-select__option--active",
                  o.value === value && "choice-select__option--selected",
                )}
                onMouseEnter={() => setActive(i)}
                // mousedown, not click, so focus never leaves the button — it is what a screen
                // reader is reading the choice from.
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(i);
                }}
              >
                {o.label}
              </li>
            ))}
          </ul>
        </FloatingLayer>
      )}
    </div>
  );
}

export function Check({
  children,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { children: ReactNode }) {
  return (
    <label className={cx("check", className)}>
      <input type="checkbox" {...props} />
      <span className="check__text">{children}</span>
    </label>
  );
}

export function Strength({ value = 3 }: { value?: 0 | 1 | 2 | 3 | 4 }) {
  return (
    <span className="strength" aria-label={`Password strength ${value} of 4`}>
      {[0, 1, 2, 3].map((index) => (
        <span key={index} className={cx("strength__bar", index < value && "is-on")} />
      ))}
    </span>
  );
}

export function StatusDot({ className }: { className?: string }) {
  return <span className={cx("status-dot", className)} />;
}

export function Badge({
  variant = "neutral",
  children,
  dot = true,
  className,
}: {
  variant?: BadgeVariant;
  children: ReactNode;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span className={cx("badge", `badge--${variant}`, className)}>
      {dot && <StatusDot />}
      {children}
    </span>
  );
}

export function Chip({
  filter,
  pressed,
  variant,
  children,
}: {
  filter?: boolean;
  pressed?: boolean;
  variant?: BadgeVariant;
  children: ReactNode;
}) {
  return (
    <span className={cx("chip", filter && "chip--filter", variant && `badge--${variant}`)} aria-pressed={pressed}>
      {children}
    </span>
  );
}

export function Needs({ type, children }: { type: "clar" | "gate"; children: ReactNode }) {
  return (
    <span className={cx("needs", `needs--${type}`)}>
      <StatusDot />
      {children}
    </span>
  );
}

export function Avatar({
  children,
  size,
  label,
}: {
  children: ReactNode;
  size?: "sm" | "lg";
  label?: string;
}) {
  return (
    <span className={cx("avatar", size && `avatar--${size}`)} aria-label={label}>
      {children}
    </span>
  );
}

export function AvatarGroup({ children, label }: { children: ReactNode; label: string }) {
  return (
    <span className="avatar-group" aria-label={label}>
      {children}
    </span>
  );
}

export function Card({
  attention,
  children,
  className,
}: HTMLAttributes<HTMLDivElement> & { attention?: boolean }) {
  return <div className={cx(attention ? "card--attention" : "card", className)}>{children}</div>;
}

export function CardBody({ children, className, style }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cx("card__body", className)} style={style}>
      {children}
    </div>
  );
}

export function Panel({
  title,
  actions,
  children,
  flush,
  className,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  className?: string;
}) {
  return (
    <section className={cx("panel", className)}>
      {title && (
        <div className="panel__header">
          <h2 className="panel__title">{title}</h2>
          {actions && (
            <>
              <span className="u-spacer" />
              {actions}
            </>
          )}
        </div>
      )}
      <div className={flush ? "panel__body--flush" : "panel__body"}>{children}</div>
    </section>
  );
}

export function Tabs({
  tabs,
  active,
  onSelect,
}: {
  tabs: Array<{ id: string; label: string }>;
  active: string;
  onSelect?: (id: string) => void;
}) {
  return (
    <div className="tabs">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={cx("tab", active === tab.id && "tab--active")}
          onClick={() => onSelect?.(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

type TableRow =
  | ReactNode[]
  | {
      cells: ReactNode[];
      className?: string;
      style?: CSSProperties;
      /** Makes the WHOLE row the control that picks this item (Bugs S.No 189). */
      onSelect?: () => void;
      selected?: boolean;
      /** What a screen reader announces for the row, when the cells alone don't read well. */
      selectLabel?: string;
    };

/** Everything a click can land on that is already a control of its own. A link inside a
 *  selectable row must navigate and NOT also select — otherwise "Preview" would quietly change
 *  the selection on its way out. */
const OWN_CONTROL = "a,button,input,select,textarea,label,summary,[role='button']";

export function Table({
  headers,
  rows,
  matrix,
}: {
  headers: ReactNode[];
  rows: TableRow[];
  matrix?: boolean;
}) {
  // Row selection is OPT-IN, per row. Every existing table in the platform passes cells and
  // nothing else, and behaves exactly as it did — the grid semantics below only switch on for a
  // table that actually has selectable rows.
  const picks = rows.map((row) => (Array.isArray(row) ? undefined : row.onSelect));
  const selectable = picks.some(Boolean);
  const anySelected = rows.some((row) => !Array.isArray(row) && row.onSelect && row.selected);
  const firstPick = picks.findIndex(Boolean);

  // Arrow keys move between rows. Walking the DOM keeps this local to the component and correct
  // whatever the caller filtered or sorted, rather than making every caller pass an index.
  const step = (from: HTMLElement, dir: 1 | -1) => {
    let next = dir === 1 ? from.nextElementSibling : from.previousElementSibling;
    while (next && !(next as HTMLElement).dataset.pick) {
      next = dir === 1 ? next.nextElementSibling : next.previousElementSibling;
    }
    if (next instanceof HTMLElement) {
      next.focus();
      next.click();
    }
  };

  return (
    <table
      className={cx("table table--in-panel", matrix && "table--matrix")}
      role={selectable ? "grid" : undefined}
    >
      <thead>
        <tr>{headers.map((head, index) => <th key={index}>{head}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, rowIndex) => {
          const cells = Array.isArray(row) ? row : row.cells;
          const className = Array.isArray(row) ? undefined : row.className;
          const style = Array.isArray(row) ? undefined : row.style;
          const pick = picks[rowIndex];
          const selected = Array.isArray(row) ? false : Boolean(row.selected);
          const label = Array.isArray(row) ? undefined : row.selectLabel;
          // Roving tab stop: the list is ONE stop in the tab order, not one per row. With
          // nothing selected the first row holds it, so the list is still reachable.
          const tabbable = selected || (!anySelected && rowIndex === firstPick);
          return (
            <tr
              key={rowIndex}
              className={cx(className, pick && "table__row--pick", selected && "table__row--sel")}
              style={style}
              data-pick={pick ? "1" : undefined}
              aria-selected={pick ? selected : undefined}
              aria-label={label}
              tabIndex={pick ? (tabbable ? 0 : -1) : undefined}
              onClick={
                pick
                  ? (event) => {
                      if ((event.target as HTMLElement).closest(OWN_CONTROL)) return;
                      pick();
                    }
                  : undefined
              }
              onKeyDown={
                pick
                  ? (event) => {
                      if ((event.target as HTMLElement).closest(OWN_CONTROL)) return;
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        pick();
                      } else if (event.key === "ArrowDown") {
                        event.preventDefault();
                        step(event.currentTarget, 1);
                      } else if (event.key === "ArrowUp") {
                        event.preventDefault();
                        step(event.currentTarget, -1);
                      }
                    }
                  : undefined
              }
            >
              {cells.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function Switch({ label, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="switch" aria-label={label}>
      <input type="checkbox" {...props} />
      <span className="switch__track" />
      <span className="switch__thumb" />
    </label>
  );
}

export function LifecycleRail({
  nodes,
  loop,
  branch,
}: {
  nodes: Array<{
    label: string;
    state: string;
    tone: "done" | "current" | "upcoming" | "running" | "needs" | "failed";
    mark: ReactNode;
  }>;
  loop?: ReactNode;
  branch?: ReactNode;
}) {
  return (
    <>
      {loop && <span className="rail__loop">{loop}</span>}
      <div className="rail">
        {nodes.map((node) => (
          <div key={`${node.label}-${node.state}`} className={cx("rail__node", `rail__node--${node.tone}`)}>
            <span className="rail__dot">{node.mark}</span>
            <span className="rail__label">{node.label}</span>
            <span className="rail__state">{node.state}</span>
          </div>
        ))}
      </div>
      {branch && <p className="rail__branch">{branch}</p>}
    </>
  );
}

export function Board({ children }: { children: ReactNode }) {
  return <div className="board">{children}</div>;
}

export function BoardCol({ title, count, children }: { title: ReactNode; count: ReactNode; children: ReactNode }) {
  return (
    <div className="board__col">
      <div className="board__col-head">
        <span className="board__col-title">{title}</span>
        <span className="u-spacer" />
        <span className="board__col-count">{count}</span>
      </div>
      <div className="board__list">{children}</div>
    </div>
  );
}

export function WiCard({ children, selected }: { children: ReactNode; selected?: boolean }) {
  return <div className={cx("wi-card", selected && "wi-card--selected")}>{children}</div>;
}

export function GatePanel({ children, attention }: { children: ReactNode; attention?: boolean }) {
  return (
    <Card attention={attention} className="gate-panel">
      <CardBody>{children}</CardBody>
    </Card>
  );
}

export function CriteriaList({ children }: { children: ReactNode }) {
  return <div className="criteria-list">{children}</div>;
}

export function CriteriaItem({ met, children }: { met?: boolean; children: ReactNode }) {
  return (
    <label className={cx("criteria-item", met && "criteria-item--met")}>
      <input type="checkbox" defaultChecked={met} />
      <span className="criteria-item__text">{children}</span>
    </label>
  );
}

export function ClarificationCard({ children }: { children: ReactNode }) {
  return (
    <Card className="clar-card">
      <CardBody>{children}</CardBody>
    </Card>
  );
}

export function SorChip({ vendor, children }: { vendor: "confluence" | "jira" | "figma" | "github" | "xray"; children: ReactNode }) {
  return (
    <span className={cx("sor-chip", `sor-chip--${vendor}`)}>
      <span className="sor-chip__glyph">{String(children).charAt(0)}</span>
      {children}
    </span>
  );
}

export function ArtifactRow({ children }: { children: ReactNode }) {
  return <div className="artifact-row">{children}</div>;
}

export function Console({ lines }: { lines: ReactNode[] }) {
  return (
    <div className="console">
      {lines.map((line, index) => (
        <div className="console__line" key={index}>{line}</div>
      ))}
    </div>
  );
}

export function Toast({ children, variant = "info" }: { children: ReactNode; variant?: BannerVariant }) {
  return <div className={cx("toast", `toast--${variant}`)}>{children}</div>;
}

export function Modal({
  title,
  children,
  footer,
  onClose,
  inline,
}: {
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  onClose?: () => void;
  inline?: boolean;
}) {
  useEscapeToClose(inline ? undefined : onClose);
  const panel = (
    <div className="modal" role="dialog" aria-modal={!inline}>
      <div className="modal__header">
        <h3 className="modal__title">{title}</h3>
        <button className="modal__close" aria-label="Close" onClick={onClose}>✕</button>
      </div>
      <div className="modal__body">{children}</div>
      {footer && <div className="modal__footer">{footer}</div>}
    </div>
  );
  if (inline) return panel;
  return (
    <div
      className="scrim-overlay scrim-overlay--center"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      {panel}
    </div>
  );
}

/**
 * Ask before doing something, in one shape everywhere.
 *
 * Four screens had each hand-rolled this out of `Modal` plus a two-button footer plus the
 * `WriteError` / `Spinner` pair, and two of them only asked SOME of the time — a first-ever phase
 * trigger fired with no question at all. Asking inconsistently is worse than not asking: it teaches
 * people that the absence of a dialog means the action is small.
 *
 * Deliberately thin. It owns the shape of the question (title, body, two buttons, the pending
 * spinner and where an error appears) and nothing about the decision itself, so a caller that needs
 * a reason field, a warning banner or a list of consequences just passes them as children.
 *
 * `danger` is for the irreversible ones. It does not add a second confirmation — a dialog that
 * takes two clicks to agree with gets clicked twice without being read.
 */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  onConfirm,
  onClose,
  busy,
  error,
  errorFallback,
  danger,
  confirmDisabled,
}: {
  title: ReactNode;
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onClose: () => void;
  busy?: boolean;
  error?: unknown;
  errorFallback?: string;
  danger?: boolean;
  confirmDisabled?: boolean;
}) {
  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{cancelLabel}</Button>
          <Button
            variant={danger ? "danger" : "primary"}
            disabled={busy || confirmDisabled}
            onClick={onConfirm}
          >
            {busy ? <Spinner /> : confirmLabel}
          </Button>
        </>
      }
    >
      <div className="u-stack">
        {children}
        {/* Below the body, above the buttons: the reader has already been told what the action is,
            and an error belongs next to the button that produced it rather than at the top where it
            displaces the question. */}
        {error ? <WriteError detail={error} fallback={errorFallback} /> : null}
      </div>
    </Modal>
  );
}

export function Drawer({
  title,
  children,
  footer,
  onClose,
  inline,
}: {
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  onClose?: () => void;
  inline?: boolean;
}) {
  useEscapeToClose(inline ? undefined : onClose);
  const panel = (
    <div className="drawer__panel" role="dialog" aria-modal={!inline}>
      <div className="drawer__header">
        <h3 className="drawer__title">{title}</h3>
        <button className="modal__close" aria-label="Close" onClick={onClose}>✕</button>
      </div>
      <div className="drawer__body">{children}</div>
      {footer && <div className="drawer__footer">{footer}</div>}
    </div>
  );
  if (inline) return <div className="drawer">{panel}</div>;
  return (
    <div
      className="scrim-overlay scrim-overlay--right"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      {panel}
    </div>
  );
}

export function Banner({ children, variant = "info", title }: { children: ReactNode; variant?: BannerVariant; title?: ReactNode }) {
  return (
    <div className={cx("banner", `banner--${variant}`)}>
      <span className="banner__icon">!</span>
      <div className="banner__body">
        {title && <div className="banner__title">{title}</div>}
        {children}
      </div>
    </div>
  );
}

/** One line on screen; the rest a click away.
 *
 * **Why it exists.** Several panels open with three or four lines of explanation that is worth
 * reading exactly once and is then re-read past on every visit, pushing the controls somebody
 * came for below the fold. This is the middle ground between keeping all of it and deleting it:
 * the sentence that matters stays visible, the detail stays reachable.
 *
 * **Why `<details>` and not a hover tooltip.** A *hover-only* tooltip cannot be opened from a
 * keyboard and does not exist on a touch screen — this platform's whole job is to find that
 * defect on other people's sites, and shipping one in its own UI would be indefensible. The
 * browser's own disclosure element is focusable, operable with Enter and Space, and announced
 * with its expanded state by a screen reader, with nothing added here. `summary` is a real
 * button to assistive technology; do not put another one inside it.
 *
 * **Which of the two to reach for.** `Tooltip` below is the accessible tooltip that objection
 * asks for — it opens on focus and tap as well as hover. Use it for a short aside about one
 * control or phrase. Use `Disclosure` when the hidden part is more than a sentence or two, or
 * contains anything interactive: a tooltip is a *description*, and a description a reader has to
 * navigate into is the wrong container.
 */
export function Disclosure({ summary, children, className }: {
  summary: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <details className={cx("disclosure", className)}>
      <summary className="disclosure__summary">{summary}</summary>
      <div className="disclosure__body">{children}</div>
    </details>
  );
}

/** A short aside about one control or phrase — the platform's first tooltip.
 *
 * **The objection this had to answer.** `Disclosure` above exists partly because the usual
 * hover tooltip is unreachable by keyboard and absent on touch, and a product that sells finding
 * that defect cannot ship it. So this is not the usual hover tooltip:
 *
 *   * the trigger is a real `<button>`, so Tab reaches it and Enter/Space work;
 *   * it opens on **focus** and on **tap**, not only on hover;
 *   * **Escape** closes it while the trigger keeps focus;
 *   * the pointer can travel from the trigger *into* the bubble without it vanishing, and it
 *     never times out — WCAG 2.2 §1.4.13 (Content on Hover or Focus) asks for exactly these
 *     three: dismissible, hoverable, persistent;
 *   * `aria-describedby` ties it to its trigger, so a screen reader reads it as that control's
 *     description rather than as loose text floating in the page.
 *
 * **Never put anything interactive inside it.** A link or button in a tooltip cannot be reached
 * — the tooltip closes when focus leaves the trigger. That content wants `Disclosure`.
 *
 * **Never hide anything here that the user must read.** It is a description; treat the visible
 * sentence as the whole message and this as the part someone may never open.
 */
export function Tooltip({ children, label = "More information", trigger, placement = "above" }: {
  children: ReactNode;
  label?: string;
  trigger?: ReactNode;
  /** `below` for a trigger near the top of the page, where an upward bubble is off-screen. */
  placement?: "above" | "below";
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const wrapRef = useRef<HTMLSpanElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const bubbleRef = useRef<HTMLSpanElement>(null);
  const close = useCallback(() => setOpen(false), []);
  // Only while open: a description that is always present is announced on every visit to the
  // trigger, which is how one helpful sentence turns into noise on a screen full of them.
  useEscapeToClose(open ? close : undefined);
  // A tap elsewhere closes it. The trigger's blur usually did that already, but a tap does not
  // always move focus (Safari on iOS never focuses a tapped button), and now that the bubble is
  // drawn in the floating layer (S.No 166) it is outside the wrapper, so the rule is written down.
  useDismissable(open, close, wrapRef, undefined, bubbleRef);
  useFloatingPosition(open, triggerRef, bubbleRef, {
    align: "center", preferAbove: placement === "above", gap: 6,
  });

  return (
    <span
      ref={wrapRef}
      className="tip"
      // On the WRAPPER, not the trigger — the bubble belongs to it, so moving the pointer onto
      // the bubble to read a long sentence does not count as leaving (§1.4.13 "hoverable").
      // That still holds with the bubble drawn in the floating layer: React delivers enter and
      // leave through its own component tree, where the bubble is still the wrapper's child.
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        ref={triggerRef}
        type="button"
        className={trigger ? "tip__trigger tip__trigger--bare" : "tip__trigger"}
        aria-label={trigger ? undefined : label}
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((was) => !was)}
      >
        {/* The marker is a letter, not a symbol: an earlier icon in this file was written as an
            escape, arrived as a raw control byte and shipped as a tofu box. "i" cannot be
            mis-encoded and needs no font installed. The circle around it is drawn in CSS. */}
        {trigger ?? <span aria-hidden="true">i</span>}
      </button>
      {open && (
        <FloatingLayer>
          <span
            ref={bubbleRef}
            role="tooltip"
            id={id}
            className={cx(
              "popover-layer",
              "tip__bubble",
              placement === "below" && "tip__bubble--below",
            )}
          >
            {children}
          </span>
        </FloatingLayer>
      )}
    </span>
  );
}

export function Tile({ num, label, sub }: { num: ReactNode; label: ReactNode; sub?: ReactNode }) {
  return (
    <div className="tile">
      <div className="tile__num">{num}</div>
      <div className="tile__label">{label}</div>
      {sub && <div className="tile__sub">{sub}</div>}
    </div>
  );
}

export function Todo({ icon, type, title, meta, action }: { icon: ReactNode; type: "gate" | "clar" | "run"; title: ReactNode; meta: ReactNode; action: ReactNode }) {
  return (
    <div className="todo">
      <span className={cx("todo__icon", `todo__icon--${type}`)}>{icon}</span>
      <div className="todo__main">
        <div className="todo__title">{title}</div>
        <div className="todo__meta">{meta}</div>
      </div>
      {action}
    </div>
  );
}

export function Segmented({ options, active }: { options: string[]; active: string }) {
  return (
    <span className="segmented">
      {options.map((option) => (
        <button key={option} aria-pressed={option === active}>{option}</button>
      ))}
    </span>
  );
}

// A stable, always-visible per-capability glyph so a card reads before any vendor is connected
// (Bugs.xlsx row 37: icons were blank until connection because the logo derived from the vendor
// name, which is "Not connected" until then). Keyed by the capability, not the vendor.
const CAP_GLYPH: Record<string, string> = {
  docstore: "Do",
  tasktracker: "Ta",
  designsource: "De",
  codehost: "Co",
  testmgmt: "Te",
};

export function CapCard({
  vendor,
  capability,
  capabilityKey,
  status,
  failed,
  children,
}: {
  vendor: string;
  capability: string;
  capabilityKey?: string;
  status: ReactNode;
  failed?: boolean;
  children?: ReactNode;
}) {
  // Show the vendor logo once a real vendor is bound; before that fall back to the capability
  // icon (always visible) rather than a broken initial of "Not connected".
  const hasVendor = Boolean(vendor) && vendor !== "Not connected";
  const glyph = hasVendor ? vendor.charAt(0) : CAP_GLYPH[capabilityKey ?? ""] ?? "•";
  const logoModifier = hasVendor
    ? `cap-card__logo--${vendor.toLowerCase()}`
    : `cap-card__logo--cap-${capabilityKey ?? "unknown"}`;
  return (
    <div className={cx("cap-card", failed && "cap-card--failed")}>
      <div className="cap-card__head">
        <span className={cx("cap-card__logo", logoModifier)}>{glyph}</span>
        <div>
          <div className="cap-card__cap">{capability}</div>
          <div className="cap-card__vendor">{vendor}</div>
        </div>
      </div>
      {children}
      <div className="cap-card__foot">{status}</div>
    </div>
  );
}

export function Breadcrumb({
  items,
}: {
  items: Array<string | { label: string; href: string }>;
}) {
  return (
    <nav className="breadcrumb">
      {items.map((item, index) => {
        const label = typeof item === "string" ? item : item.label;
        const href = typeof item === "string" ? undefined : item.href;
        const last = index === items.length - 1;
        return (
          <span key={label}>
            {index > 0 && <span className="sep">›</span>}
            {!last && href ? (
              <RouterLink to={href}>{label}</RouterLink>
            ) : (
              <span className="here">{label}</span>
            )}
          </span>
        );
      })}
    </nav>
  );
}

export function MetaRow({ children }: { children: ReactNode }) {
  return <div className="meta-row">{children}</div>;
}

export function Kv({ rows }: { rows: Array<[ReactNode, ReactNode]> }) {
  return (
    <dl className="kv">
      {rows.map(([key, value], index) => (
        <div key={index}>
          <dt>{key}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

// Bugs.xlsx row 14: the Copy buttons on the token + command blocks had no handler (nothing
// happened). This writes the value to the clipboard, with a legacy execCommand fallback for
// non-secure contexts, and confirms with a brief "Copied!".
export function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback for browsers / contexts without the async clipboard API.
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
      } catch {
        /* give up silently — the value is still visible to copy manually */
      }
      document.body.removeChild(ta);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      type="button"
      className={cx("cmd-copy", copied && "cmd-copy--done", className)}
      onClick={onCopy}
      aria-label={copied ? "Copied to clipboard" : "Copy to clipboard"}
    >
      {copied ? "✓ Copied!" : "Copy"}
    </button>
  );
}

export function CmdBlock({ rows }: { rows: string[] }) {
  return (
    <div className="cmd-block">
      {rows.map((row) => (
        <div className="cmd-row" key={row}>
          <span className="cmd-row__text"><span className="prompt">$ </span>{row}</span>
          <CopyButton text={row} />
        </div>
      ))}
    </div>
  );
}

export function TokenReveal({ token }: { token: string }) {
  return (
    <div className="token-reveal">
      <span>{token}</span>
      <span className="u-spacer" />
      <CopyButton text={token} />
    </div>
  );
}

export function Vstep({ state, num, title, desc }: { state?: "done" | "active" | "running"; num: ReactNode; title: ReactNode; desc: ReactNode }) {
  return (
    <div className={cx("vstep", state && `vstep--${state}`)}>
      <span className="vstep__num">{num}</span>
      <div className="vstep__body">
        <div className="vstep__title">{title}</div>
        <div className="vstep__desc">{desc}</div>
      </div>
    </div>
  );
}

export function ConnStatus({ state, children }: { state: "waiting" | "connected" | "offline"; children: ReactNode }) {
  return (
    <div className={cx("conn-status", `conn-status--${state}`)}>
      {state === "waiting" ? <span className="spinner" /> : <StatusDot />}
      {children}
    </div>
  );
}

export function Dropzone({ children }: { children: ReactNode }) {
  return <div className="dropzone">{children}</div>;
}

export function Assess({ state, children }: { state: "complete" | "partial" | "missing"; children: ReactNode }) {
  return <span className={cx("assess", `assess--${state}`)}>{children}</span>;
}

export function VersionRow({ tag, children }: { tag: ReactNode; children: ReactNode }) {
  return (
    <div className="version-row">
      <span className="version-row__tag">{tag}</span>
      {children}
    </div>
  );
}

export function DocPreview({ children }: { children: ReactNode }) {
  return <div className="doc-preview prose">{children}</div>;
}

export { Markdown } from "./Markdown";

export function DiagramFrame({ children }: { children: ReactNode }) {
  return <div className="diagram-frame">{children}</div>;
}

export function GraphCanvas({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div className="graph-canvas" style={style}>{children}</div>;
}

export function GraphLegend({ children }: { children: ReactNode }) {
  return <div className="graph-legend">{children}</div>;
}

export function AuthSplit({
  children,
  tagline = "Run your whole software lifecycle with AI — and human approval gates.",
  sub,
}: {
  children: ReactNode;
  tagline?: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="auth">
      <div className="auth__brand">
        <div className="auth__brand-logo">
          <span className="auth__brand-mark" aria-hidden="true" />
          <span className="auth__brand-word">edvensoft</span>
        </div>
        <div className="auth__tagline">{tagline}</div>
        {sub && <div className="auth__sub">{sub}</div>}
      </div>
      <div className="auth__form">{children}</div>
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

export function Transcript({ children }: { children: ReactNode }) {
  return <div className="transcript">{children}</div>;
}

const TURN_LABEL: Record<"agent" | "tool" | "human", string> = {
  agent: "Agent",
  tool: "Tool",
  human: "You",
};

export function Turn({ role, children }: { role: "agent" | "tool" | "human"; children: ReactNode }) {
  return (
    <div className={cx("turn", `turn--${role}`)}>
      <span className="turn__role">{TURN_LABEL[role]}</span>
      <div className="turn__body">{children}</div>
    </div>
  );
}

export function EmptyState({ title, text, action }: { title: ReactNode; text: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty__title">{title}</div>
      <div className="empty__text">{text}</div>
      {action}
    </div>
  );
}

/** A request FAILED — which is not the same thing as there being nothing to show.
 *
 * **Why this exists.** Bugs S.No 220: five list screens branched on "loading?" and then on "is
 * the list empty?", and a failed request produces an empty list. So a completely broken backend
 * rendered as a calm, healthy, brand-new workspace — "You're all caught up", "No lineage yet".
 * The QA audit found the sharpest consequence: several written test cases would PASS against a
 * dead server, because "the dashboard shows no pending gates" is exactly what they assert. It
 * also costs support time, because a user whose session or network has failed sees no error to
 * report.
 *
 * **Why a shared primitive rather than five inline banners.** The whole finding is that five
 * screens independently forgot the same case. One component makes the omission visible in review,
 * and it is the only way the sixth screen built next month inherits the behaviour.
 *
 * Render it BEFORE the empty check, never after — `if (q.isError) return <ErrorState … />`.
 */
export function ErrorState({
  title,
  detail,
  onRetry,
  subject,
  guard = "generic",
  panel = false,
}: {
  /** Only used when the server refused this particular request and said why (a 4xx). */
  title?: ReactNode;
  detail?: unknown;
  onRetry?: () => void;
  /** What the reader cannot see, for the no-access title: "this project's pages". */
  subject?: string;
  /** `a11y` swaps the closing line for the one about conformance. */
  guard?: "generic" | "a11y";
  /** Wrap in a Panel, with the cause as its title — the accessibility screens' shape. */
  panel?: boolean;
}) {
  // Bugs S.No 248, and the team's rule of 8 September: every word here is for the CLIENT, who
  // did not build this and has no code to read. So no status codes, no thrown text, no
  // "Technical details" disclosure, and no instruction that needs access they don't have.
  // Four elements and no fifth: the CAUSE as a title, ONE line of what happened, the button,
  // then one line so an empty screen is never mistaken for a clean result.
  //
  // The cause is real information now rather than a guess — `req` classifies every failure (see
  // `Failure` in api.ts). Before that, an unreachable server and a broken one were the same
  // unreadable string, which is why this used to print "Failed to fetch" at a product owner.
  const failure = failureOf(detail);

  // The server's own words, when the server chose them for a person to read. `detail` is
  // whatever the query threw, so it is typed `unknown` on purpose.
  const said =
    (typeof detail === "string" && detail) ||
    (detail && typeof detail === "object"
      ? ((detail as { message?: string }).message ??
         (detail as { detail?: string }).detail ??
         "")
      : "") ||
    "";

  const head =
    failure === "offline"
      ? "Can't reach the SDLC app right now"
      : failure === "server"
        ? "Something went wrong on our side"
        : failure === "denied"
          ? `You don't have access to ${subject ?? "this"}`
          : (title ?? "This didn't load");

  const line =
    failure === "offline"
      ? "Your browser couldn't connect."
      : failure === "server"
        ? "The app couldn't load this. Nothing you did caused it."
        : failure === "denied"
          ? said || "You are not a member of this project."
          : said || "The app couldn't load this.";

  // Retrying a permission problem cannot work, and a control that cannot work is its own small
  // lie — so the button is dropped for `denied` even when a caller passed a retry.
  const retry = failure === "denied" ? undefined : onRetry;

  const closing =
    failure === "denied"
      ? "Nothing is wrong — this screen simply isn't yours to see."
      : guard === "a11y"
        ? failure === "offline"
          ? "This is a connection problem, not a result — it says nothing about your application's accessibility."
          : "This is a problem with the app, not a result — it says nothing about your application's accessibility."
        : "This screen is empty because it didn't load — not because there is nothing here.";

  const body = (
    <>
      <Banner variant={failure === "denied" ? "info" : "danger"} title={panel ? undefined : head}>
        <div className="empty__text">{line}</div>
      </Banner>
      {failure === "denied" && (
        <p className="t-sm" style={{ margin: "var(--space-3) 0 0" }}>
          Ask a workspace admin to add you to this project, then reload.
        </p>
      )}
      {retry && (
        <div style={{ marginTop: "var(--space-3)" }}>
          <Button variant="primary" size="sm" onClick={retry}>
            Try again
          </Button>
        </div>
      )}
      <p className="t-sm u-muted" style={{ margin: "var(--space-3) 0 0" }}>
        {closing}
      </p>
    </>
  );

  return panel ? <Panel title={head}>{body}</Panel> : <div>{body}</div>;
}

/** The counterpart to `ErrorState` for a WRITE that failed (Bugs S.No 219).
 *
 * There was one of these for reads and none for writes, so four screens each invented their
 * own spelling and three more gave up and showed nothing at all — a resend that silently did
 * nothing, a repository refusal caught and thrown away, a password rejected by a form that
 * just sat there. One shared piece is what stops the eighth screen inventing an eighth.
 *
 * Deliberately NO retry button. Retrying a read is a refetch; retrying a write is submitting
 * again, and a "Try again" that quietly re-sends an invitation is its own bug. The control
 * that failed is still on screen — that is the retry.
 */
/** The sentence a failed write should show, for the places a whole banner does not fit.
 *
 * Screen Words group 5 asked for ONE rule for every error banner. `WriteError` had that rule in
 * its body, so the handful of screens that show a failure as a line of red text under a compact
 * form — the clarification answer, Create work item, Disconnect machine — could not share it and
 * printed `error.message` instead. Which means those were exactly the places still showing the
 * browser's `Failed to fetch` and `500 Internal Server Error`.
 *
 * `fallback` replaces only the last case (a 4xx that gave no reason), where a screen usually has
 * a better sentence than the generic one because it knows what was being attempted.
 */
export function writeErrorSentence(detail?: unknown, fallback?: string): string {
  // `detail` is whatever the mutation threw, so it is `unknown` on purpose. An ApiError's
  // message is already humanized by `humanizeError` in api.ts — DRF's nested validation shape
  // has been walked down to the leaf sentences a person can actually act on.
  //
  // A 4xx is the case worth keeping verbatim: the server refused this particular thing and said
  // why, in words, and that sentence is the whole value of this banner. The other two kinds had
  // the same fault as the read path (Bugs S.No 248) — a save attempted with no connection showed
  // the browser's `Failed to fetch`, and a 500 showed a JSON parse error. Neither is for a client.
  const failure = failureOf(detail);
  const said =
    (typeof detail === "string" && detail) ||
    (detail && typeof detail === "object"
      ? ((detail as { message?: string }).message ??
         (detail as { detail?: string }).detail ??
         "")
      : "") ||
    "";
  if (failure === "offline") {
    return "Your browser couldn't connect, so nothing was saved. Try again.";
  }
  if (failure === "server") {
    return "Something went wrong on our side, so nothing was saved. Nothing you did caused it.";
  }
  if (failure === "denied") {
    return said || "You don't have permission to do that.";
  }
  return (
    said || fallback || "That wasn't accepted, and no reason was given. Nothing was changed."
  );
}

export function WriteError({
  title = "That didn't work",
  detail,
  fallback,
}: {
  title?: ReactNode;
  detail?: unknown;
  fallback?: string;
}) {
  return (
    <Banner variant="danger" title={title}>
      <div className="empty__text">{writeErrorSentence(detail, fallback)}</div>
    </Banner>
  );
}

export function Skeleton({ kind = "line" }: { kind?: "line" | "title" | "block" }) {
  return <div className={cx("skeleton", `skeleton--${kind}`)} />;
}
