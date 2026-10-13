import {
  ArtifactRow,
  Assess,
  AuthSplit,
  Avatar,
  AvatarGroup,
  Badge,
  Banner,
  Board,
  BoardCol,
  Breadcrumb,
  Button,
  CapCard,
  Card,
  CardBody,
  Check,
  Chip,
  ClarificationCard,
  CmdBlock,
  ConnStatus,
  Console,
  CriteriaItem,
  CriteriaList,
  DiagramFrame,
  Disclosure,
  DocPreview,
  Drawer,
  Dropzone,
  EmptyState,
  Field,
  GatePanel,
  GraphCanvas,
  GraphLegend,
  Input,
  LifecycleRail,
  MetaRow,
  Modal,
  Needs,
  Panel,
  Segmented,
  Select,
  Skeleton,
  SorChip,
  Strength,
  Switch,
  Table,
  Textarea,
  Tile,
  Todo,
  TokenReveal,
  Tooltip,
  Transcript,
  Turn,
  VersionRow,
  Vstep,
  WiCard,
} from "../ui";
import { Clarifications } from "../../features/lifecycle/Clarifications";
import { Markdown } from "../ui/Markdown";

const DEMO_MD = [
  "### Container Diagram (C4 Level 2)",
  "",
  "```mermaid",
  "graph TD",
  "  Browser[Browser SPA] --> API[FastAPI REST API]",
  "  API --> DB[(PostgreSQL 16)]",
  "  API --> Auth[Auth Service - JWT/bcrypt]",
  "  API --> Cache[(Redis Cache)]",
  "```",
  "",
  "### NFR-to-Architecture Traceability Matrix",
  "",
  "| NFR ID | NFR Statement | Target | Architectural Response | Decision / Pattern | ADR |",
  "| --- | --- | --- | --- | --- | --- |",
  "| NFR-PE-001 | API P95 latency all endpoints except registration | <= 300 ms | FastAPI `async def` endpoints + asyncpg connection pool (pool_size=10) + B-tree indexed PostgreSQL queries on (user_id, date) | Async I/O + Connection Pooling | ADR-002 |",
  "| NFR-PE-002 | Registration P95 latency | <= 500 ms | `bcrypt.hashpw(cost=12)` in `asyncio.run_in_executor` (~150 ms) + single async DB INSERT (~5 ms) | bcrypt in executor (non-blocking) | ADR-004 |",
].join("\n");

// Realistic Task-Breakdown description (was shown as raw markdown before S.No 167).
const WI_DESC_MD = [
  "**Type:** Frontend | **Estimate:** S = 1 SP (~4h) | **Critical Path:** Yes",
  "",
  "**What to build:** A Zustand auth store (`src/stores/authStore.ts`) with persist middleware.",
  "",
  "State shape: `{ accessToken: string | null, isAuthenticated: boolean }`. Actions:",
  "",
  "- `setTokens(access, refresh)` — sets both tokens, sets `isAuthenticated=true`",
  "- `logout()` — clears all state and removes the `spendlog_auth` localStorage key",
  "",
  "**Acceptance Criteria:**",
  "",
  "- [ ] After `setTokens()`, `localStorage` contains the tokens and `isAuthenticated=true`",
  "- [ ] After `logout()`, the auth key is removed and `isAuthenticated=false`",
].join("\n");

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel" style={{ marginBottom: "var(--space-6)" }}>
      <div className="panel__header"><h2 className="panel__title">{title}</h2></div>
      <div className="panel__body u-stack">{children}</div>
    </section>
  );
}

export function DevComponents() {
  return (
    <main id="screen">
      <div className="canvas-pad">
        <div className="page-head">
          <div className="page-head__titles">
            <h1 className="t-h1">S-00 Component Library</h1>
            <p className="page-head__sub">React port of the signed-off gallery classes.</p>
          </div>
        </div>

        <Section title="Buttons">
          <div className="u-row u-wrap">
            <Button variant="primary">Primary action</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="danger-solid">Delete</Button>
            <Button variant="primary" disabled>Disabled</Button>
          </div>
          <div className="u-row u-wrap">
            <Button variant="primary" size="sm">Small primary</Button>
            <Button variant="secondary" size="sm">Small secondary</Button>
            <Button variant="ghost" size="sm">Small ghost</Button>
          </div>
        </Section>

        <Section title="Form fields">
          <div className="grid grid--2">
            <div>
              <Field label="Work email" help="We'll send the invite here.">
                <Input type="email" defaultValue="sarah@acme.com" />
              </Field>
              <Field label="Org / workspace name" error="That workspace name is already in use." required>
                <Input defaultValue="Acme Corp" aria-invalid="true" />
              </Field>
              <Field label="Track">
                <Select defaultValue="Greenfield"><option>Greenfield</option><option>Brownfield</option></Select>
              </Field>
            </div>
            <div>
              <Field label="Description">
                <Textarea defaultValue="Card payment gateway handling Stripe and Adyen." />
              </Field>
              <Field label="Password" help="Strong - add a symbol to max it out.">
                <Input type="password" defaultValue="password" />
                <Strength value={3} />
              </Field>
              <Check defaultChecked>Support CSV export in v1 of the analytics dashboard.</Check>
            </div>
          </div>
        </Section>

        <Section title="Status badges, chips, avatars">
          <div className="u-row u-wrap">
            <Badge variant="queued">Queued</Badge>
            <Badge variant="waiting">Dispatched waiting</Badge>
            <Badge variant="running">Running</Badge>
            <Badge variant="needs-answer">Needs answer</Badge>
            <Badge variant="gate">Awaiting gate</Badge>
            <Badge variant="done">Published</Badge>
            <Badge variant="failed">Failed</Badge>
            <Badge variant="parked">Parked for takeover</Badge>
          </div>
          <div className="u-row u-wrap">
            <Chip variant="navy">Epic</Chip>
            <Chip>Task</Chip>
            <Chip variant="orange">Defect</Chip>
            <Needs type="clar">1 Clarification</Needs>
            <Needs type="gate">Gate: PM Approval Req.</Needs>
            <Chip filter pressed>Epics</Chip>
          </div>
          <div className="u-row u-wrap">
            <Avatar size="sm">SC</Avatar>
            <Avatar>ML</Avatar>
            <Avatar size="lg">PN</Avatar>
            <AvatarGroup label="Sarah Chen, Marcus Lee, Priya Nair">
              <Avatar>SC</Avatar><Avatar>ML</Avatar><Avatar>PN</Avatar>
            </AvatarGroup>
          </div>
        </Section>

        <Section title="Tooltip and disclosure">
          <p className="t-sm u-body">
            Where the files go
            <Tooltip>
              Connecting lets the platform read the diagrams and screenshots inside your
              documents and analyse your code — all on your machine.
            </Tooltip>
          </p>
          <p className="t-sm u-body">
            Tab to the marker above: this one opens on keyboard focus and on tap, not only on
            hover, and Escape closes it. Reach for <code>Disclosure</code> instead whenever the
            hidden part runs past a sentence or two, or contains anything clickable.
          </p>
          <p className="t-sm u-body">
            A custom trigger, for a phrase inside a sentence:{" "}
            <Tooltip trigger={<span>the companion</span>}>
              The small program that runs on your own machine and does the work that must not
              leave it.
            </Tooltip>
          </p>
          <Disclosure summary="What a disclosure looks like next to it">
            <p className="t-sm u-muted">
              Longer, and safe to put a <a href="#top">link</a> in — a tooltip closes as soon as
              focus leaves its trigger, so a link inside one can never be reached.
            </p>
          </Disclosure>
        </Section>

        <section style={{ marginBottom: "var(--space-6)" }}>
          <div className="grid grid--2">
            <Card><CardBody><h3 className="t-h3">Standard card</h3><p className="t-sm u-muted">Surface container.</p></CardBody></Card>
            <Card attention><CardBody><h3 className="t-h3">Architecture Gate Review</h3><p className="t-sm u-body">Attention card.</p></CardBody></Card>
          </div>
        </section>

        <Panel title="Tabs and table" flush>
          <Table
            headers={["Run", "Phase", "Status", "Owner", "Cost"]}
            rows={[
              ["RUN-42", "Architecture", <Badge variant="gate">Awaiting gate</Badge>, "Marcus Lee", "$0.31"],
              ["RUN-41", "Requirements", <Badge variant="done">Completed</Badge>, "Sarah Chen", "$0.18"],
              ["RUN-40", "PRD", <Badge variant="needs-answer">Needs answer</Badge>, "Sarah Chen", "-"],
            ]}
          />
        </Panel>

        <Section title="Lifecycle rail">
          <LifecycleRail
            nodes={[
              { label: "Ideation", state: "Approved", tone: "done", mark: "✓" },
              { label: "Requirements", state: "Approved", tone: "done", mark: "✓" },
              { label: "PRD", state: "Approved", tone: "done", mark: "✓" },
              { label: "Architecture", state: "Gate Pending", tone: "current", mark: "●" },
              { label: "UX Design", state: "Not started", tone: "upcoming", mark: "5" },
            ]}
          />
          <LifecycleRail
            loop="Review - Implementation loop x2"
            branch="Child defect: WI-547 Signature check rejects valid test events"
            nodes={[
              { label: "Implementation", state: "PR #218", tone: "done", mark: "✓" },
              { label: "Review", state: "Running", tone: "running", mark: "" },
              { label: "Test", state: "Defect WI-547", tone: "failed", mark: "!" },
              { label: "Merge", state: "Not started", tone: "upcoming", mark: "4" },
            ]}
          />
        </Section>

        <Section title="Board and work-item card">
          <Board>
            <BoardCol title="2. Requirements" count="3">
              <WiCard>
                <div className="wi-card__top"><span className="wi-card__id">WI-510</span><Badge variant="running">AI compiling</Badge></div>
                <div className="wi-card__title">Analytics Dashboard PRD Generation</div>
                <div className="wi-card__meta"><Chip variant="navy">Epic</Chip><Needs type="clar">1 Clarification</Needs></div>
                <div className="wi-card__foot"><span>0 artifacts</span><span className="u-spacer" /><Avatar size="sm">SC</Avatar></div>
              </WiCard>
            </BoardCol>
            <BoardCol title="3. Architecture" count="1">
              <WiCard selected>
                <div className="wi-card__top"><span className="wi-card__id">WI-492</span><Needs type="gate">Review Architecture Gate</Needs></div>
                <div className="wi-card__title">Stripe Webhook Integration</div>
                <div className="wi-card__meta"><Chip variant="navy">Epic</Chip><SorChip vendor="jira">Jira</SorChip></div>
                <div className="wi-card__foot"><span>2 artifacts</span><span className="u-spacer" /><Avatar size="sm">SC</Avatar></div>
              </WiCard>
            </BoardCol>
          </Board>
        </Section>

        <section style={{ marginBottom: "var(--space-6)" }}>
          <div className="grid grid--2">
            <GatePanel attention>
              <span className="gate-panel__role">Architecture gate - required role: architect</span>
              <h3 className="t-h3">WI-492 - Stripe Webhook Integration</h3>
              <p className="t-sm u-body">Approve to publish the System Sequence Diagram.</p>
              <div className="gate-panel__actions"><Button variant="primary">Approve</Button><Button>Reject</Button></div>
            </GatePanel>
            <GatePanel>
              <span className="gate-panel__role">Criteria gate - UX Design</span>
              <p className="criteria-progress">2 of 3 criteria met</p>
              <CriteriaList>
                <CriteriaItem met>Color contrast at least 4.5:1</CriteriaItem>
                <CriteriaItem met>Keyboard navigable</CriteriaItem>
                <CriteriaItem>Focus visible on all controls</CriteriaItem>
              </CriteriaList>
            </GatePanel>
          </div>
        </section>

        <Section title="Clarification, artifacts, console">
          <ClarificationCard>
            <div className="clar-card__head"><span className="wi-card__id">WI-510</span><Badge variant="needs-answer">Requirements needs answer</Badge><span className="u-spacer" /><span className="zero-cost">Paused - no usage billed</span></div>
            <p className="t-body u-strong">Should the analytics dashboard support CSV export in v1?</p>
            <p className="clar-card__why"><span className="lbl">Why I'm asking:</span> Affects NFR scope.</p>
          </ClarificationCard>
          <ArtifactRow>
            <div className="artifact-row__main"><div className="artifact-row__title">PRD: Stripe Webhook Integration</div><div className="artifact-row__meta">v1.2 - Requirements - Published</div></div>
            <Badge variant="done">Published</Badge><SorChip vendor="confluence">Confluence</SorChip>
          </ArtifactRow>
          <Console lines={["[10:42] Agent compiling requirements", "[10:43] Artifact registered as draft v0.9"]} />
        </Section>

        <Section title="Clarifications — all-tiers gate">
          <Clarifications forceView="tiered" />
        </Section>

        <Section title="Artifact rendering — diagram + wide table (S.No 165)">
          <Markdown>{DEMO_MD}</Markdown>
        </Section>

        <Section title="Work-item description — markdown rendered in a panel (S.No 167)">
          <Panel title="Description">
            <Markdown className="prose md-body">{WI_DESC_MD}</Markdown>
          </Panel>
        </Section>

        <Section title="Toast, modal, empty, skeleton">
          <div className="grid grid--2">
            <EmptyState title="No work items yet" text="Create your first work item to start the lifecycle." action={<Button variant="primary">New Work Item</Button>} />
            <div><Skeleton kind="title" /><Skeleton /><Skeleton /><Skeleton kind="block" /></div>
          </div>
          <Modal inline title="Publish artifact" footer={<><Button>Cancel</Button><Button variant="primary">Publish</Button></>}>
            <Field label="Destination"><Input defaultValue="Confluence / PAY" /></Field>
          </Modal>
        </Section>

        <Section title="Navigation and setup additions">
          <Breadcrumb items={["Work Items", "WI-492"]} />
          <MetaRow><span className="meta-item">Created <strong>2d ago</strong></span><span className="meta-item">Owner <strong>Sarah Chen</strong></span></MetaRow>
          <TokenReveal token="rnr_3f9a...b2" />
          <CmdBlock rows={["claude", "python -m runner.companion serve --token rnr_3f9a...b2"]} />
          <ConnStatus state="waiting">Waiting for first check-in</ConnStatus>
          <ConnStatus state="connected">Connected - Sarah's MacBook</ConnStatus>
          <ConnStatus state="offline">Offline - last seen 5m ago</ConnStatus>
          <Vstep state="done" num="✓" title="Upload resources" desc="3 documents extracted." />
          <Vstep state="running" num="2" title="Index code" desc="Indexing acme/payments-api." />
        </Section>

        <Section title="Dashboard, onboarding, observability">
          <Segmented options={["Board", "List"]} active="Board" />
          <div className="grid grid--3">
            <Tile num="2" label="Gates need you" sub="architect, product_owner" />
            <Tile num="1" label="Question awaiting you" sub="WI-510 Requirements" />
            <Tile num="3" label="My runs in flight" sub="1 running" />
          </div>
          <Todo icon="▲" type="gate" title="Architecture gate" meta="required role: architect" action={<Button variant="primary" size="sm">Review</Button>} />
          <Dropzone><div className="t-body u-strong">Drag and drop documents</div><div className="t-sm u-muted">.docx .pdf .xlsx</div></Dropzone>
          <Assess state="complete">✓ Complete</Assess><Assess state="partial">~ Partial</Assess><Assess state="missing">x Missing</Assess>
          <Banner variant="warning" title="Your machine is not connected">Phases cannot run until you connect your machine.</Banner>
        </Section>

        <Section title="Preview, graph, integrations, admin">
          <div className="grid grid--2">
            <DocPreview><h1>PRD: Stripe Webhook Integration</h1><h2>Goal</h2><p>Reconcile asynchronous Stripe payment events.</p></DocPreview>
            <div>
              <DiagramFrame><span className="t-sm">System Sequence Diagram - Figma embed</span></DiagramFrame>
              <VersionRow tag="v1.2"><span className="t-sm u-strong">Current - Published</span></VersionRow>
            </div>
          </div>
          <GraphCanvas><GraphLegend><span className="graph-legend__item"><span className="graph-legend__dot" style={{ background: "var(--success)" }} />Published</span></GraphLegend></GraphCanvas>
          <div className="grid grid--3">
            <CapCard vendor="confluence" capability="Documentation store" status={<Badge variant="done">Connected</Badge>} />
            <CapCard vendor="empty" capability="Test management" status={<Badge variant="queued">Not connected</Badge>} />
            <CapCard vendor="github" capability="Code host" failed status={<Badge variant="failed">Failed</Badge>} />
          </div>
          <div className="u-row u-wrap"><Switch label="Role on" defaultChecked /><Switch label="Role off" /></div>
          <Drawer inline title="Invite teammate" footer={<><Button>Cancel</Button><Button variant="primary">Send invite</Button></>}>
            <Field label="Work email"><Input defaultValue="raj@acme.com" /></Field>
          </Drawer>
        </Section>

        <Section title="Auth split-panel and transcript">
          <AuthSplit>
            <div className="auth-card">
              <h2 className="auth-card__title">Log in</h2>
              <p className="auth-card__sub">Welcome back to Acme Corp.</p>
              <Button variant="primary" block>Log in</Button>
            </div>
          </AuthSplit>
          <Transcript>
            <Turn role="agent">Compiling requirements from the approved artifact.</Turn>
            <Turn role="tool">docstore.read("PRD") - ok</Turn>
            <Turn role="human">Answered target Confluence space: PAY</Turn>
          </Transcript>
        </Section>
      </div>
    </main>
  );
}
