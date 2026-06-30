import type {
  ButtonHTMLAttributes,
  CSSProperties,
  HTMLAttributes,
  InputHTMLAttributes,
  LabelHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { Link as RouterLink } from "react-router-dom";

type Variant =
  | "primary"
  | "secondary"
  | "ghost"
  | "danger"
  | "danger-solid";
type BadgeVariant =
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
  | "outline";
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

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx("textarea", props.className)} />;
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
  | { cells: ReactNode[]; className?: string; style?: CSSProperties };

export function Table({
  headers,
  rows,
  matrix,
}: {
  headers: ReactNode[];
  rows: TableRow[];
  matrix?: boolean;
}) {
  return (
    <table className={cx("table table--in-panel", matrix && "table--matrix")}>
      <thead>
        <tr>{headers.map((head, index) => <th key={index}>{head}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, rowIndex) => {
          const cells = Array.isArray(row) ? row : row.cells;
          const className = Array.isArray(row) ? undefined : row.className;
          const style = Array.isArray(row) ? undefined : row.style;
          return (
            <tr key={rowIndex} className={className} style={style}>
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
  nodes: Array<{ label: string; state: string; tone: "done" | "current" | "upcoming" | "running" | "failed"; mark: ReactNode }>;
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

export function Modal({ title, children, footer }: { title: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="modal">
      <div className="modal__panel">
        <div className="modal__header">
          <h3 className="modal__title">{title}</h3>
          <button className="modal__close" aria-label="Close">x</button>
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__footer">{footer}</div>}
      </div>
    </div>
  );
}

export function Drawer({ title, children, footer }: { title: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="drawer">
      <div className="drawer__panel">
        <div className="drawer__header">
          <h3 className="drawer__title">{title}</h3>
          <button className="modal__close" aria-label="Close">x</button>
        </div>
        <div className="drawer__body">{children}</div>
        {footer && <div className="drawer__footer">{footer}</div>}
      </div>
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

export function CapCard({
  vendor,
  capability,
  status,
  failed,
  children,
}: {
  vendor: string;
  capability: string;
  status: ReactNode;
  failed?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className={cx("cap-card", failed && "cap-card--failed")}>
      <div className="cap-card__head">
        <span className={cx("cap-card__logo", `cap-card__logo--${vendor.toLowerCase()}`)}>{vendor.charAt(0)}</span>
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

export function CmdBlock({ rows }: { rows: string[] }) {
  return (
    <div className="cmd-block">
      {rows.map((row) => (
        <div className="cmd-row" key={row}>
          <span className="cmd-row__text"><span className="prompt">$ </span>{row}</span>
          <button className="cmd-copy">Copy</button>
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
      <button className="cmd-copy">Copy</button>
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

export function DiagramFrame({ children }: { children: ReactNode }) {
  return <div className="diagram-frame">{children}</div>;
}

export function GraphCanvas({ children }: { children: ReactNode }) {
  return <div className="graph-canvas">{children}</div>;
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

export function Turn({ role, children }: { role: "agent" | "tool" | "human"; children: ReactNode }) {
  return (
    <div className={cx("turn", `turn--${role}`)}>
      <span className="turn__role">{role === "human" ? "You" : role}</span>
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

export function Skeleton({ kind = "line" }: { kind?: "line" | "title" | "block" }) {
  return <div className={cx("skeleton", `skeleton--${kind}`)} />;
}
