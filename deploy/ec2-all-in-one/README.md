# All-in-one EC2 — testing / staging runbook

**Audience: a DevOps engineer with no prior knowledge of this application.** Everything you
need is here; you should not have to read the app's source or its other docs.

This deploys the whole platform onto **one EC2 box**: Postgres, Temporal, the Django API,
the background worker, and the built React app behind nginx. Artifact files go to a **real
S3 bucket**. Testers then use it from a browser.

```
                      ┌──────────────────── EC2 (one box) ─────────────────────┐
  browser  ──:80──►   │  nginx ──/──► built React app (webroot volume)         │
                      │        └─/api/──► backend (Django) ──► postgres        │
  companion ──:80──►  │                     │                  └─ temporal ──┐ │
  (a developer's      │                     └──────────────────► AWS S3      │ │
   laptop, outbound   │                        worker ◄─────────────────────┘ │
   only)              │  everything except :80 binds to 127.0.0.1             │
                      └───────────────────────────────────────────────────────┘
```

### What the seven containers are, in one line each

**Every row below is a Docker container.** You do not install any of them — `docker compose`
downloads or builds all seven for you (Part D). The only things installed on the operating
system are Docker and git. See the box at the start of Part B before you `apt install`
anything.

| Container | What it is | If it's down |
|---|---|---|
| `postgres` | Postgres 16 + pgvector. Holds **all** application state **and** Temporal's own event history. | Nothing works. |
| `temporal` | Temporal server — a durable workflow engine. Every long-running job in this app is a Temporal workflow. | Jobs can't start or resume. The web app still loads. |
| `temporal-ui` | Web UI for inspecting those workflows. Operator convenience only. | No impact on the app. |
| `backend` | The Django REST API. | The app is dead (nginx serves the page, every call fails). |
| `worker` | Connects to Temporal and actually executes the workflow steps. | The UI works, but nothing ever progresses. **Easy to miss — check it.** |
| `frontend-build` | Runs once, compiles the React app into a volume, exits. | nginx has nothing to serve. |
| `nginx` | Serves the compiled app and reverse-proxies `/api` to `backend`. The only public port. | Nothing is reachable. |

**There is no MinIO** in this deployment — files go to S3. (The repo's root
`docker-compose.yml` runs MinIO for laptop development; ignore it, it is not used here.)

**How this differs from [`../shared-aws/`](../shared-aws/README.md):** that is a *hybrid*
runbook where each developer still runs the app on their laptop. This one is self-contained.
The two are alternatives — **do not follow both**.

---

# Part 0 — Before you touch AWS

## 0.1 Who does what

| # | Task | Owner |
|---|---|---|
| 1 | Provide the values in §0.2 and the secrets in §0.3 | **App team** |
| 2 | Provide repo access for the branch in §0.4 | **App team** |
| 3 | Everything in Parts A–E (AWS, box, deploy, verify) | **DevOps (you)** |
| 4 | Part F — connecting each developer's "companion" | **Each developer, on their own laptop.** Not your job; §F explains what to tell them. |

**Do not start until you have every value in §0.2 and §0.3.** Several of them are baked into
the build, so a missing one means redoing work, not just editing a file.

## 0.2 Values to collect

| Value | Example | Who provides |
|---|---|---|
| Region for the box and bucket | `ap-south-1` | You + app team |
| Public address users will type | `http://13.235.10.20` or `http://sdlc-staging.example.com` | You (allocate an **Elastic IP** — see the warning below) |
| S3 bucket name (new, dedicated) | `sdlc-artifacts-staging` | You |
| IPs allowed to reach the box | office CIDR / VPN / individual IPs | App team |
| Git branch to deploy | `develop-backup-07-09-2026` | App team (confirmed) |

> **Allocate an Elastic IP or a DNS name before you build anything.** The public address is
> **compiled into the frontend** and is also printed on-screen as the connection command each
> developer copies. A default EC2 public IP changes on every stop/start; when it changes, the
> app breaks in a way that looks like a code bug and the fix is a rebuild, not a restart.

## 0.3 Secrets to request from the app team

You cannot generate any of these. Ask for them up front, and store them somewhere better
than chat.

| Secret | What it's for | Required? |
|---|---|---|
| `ANTHROPIC_API_KEY` | AI work run *on the server* (for users who haven't connected their own laptop) | **Yes** |
| `GITHUB_TOKEN` | Reading repos and opening pull requests | **Yes** |
| Atlassian / Figma / Xray tokens | Integrations with Jira, Confluence, Figma, Xray | Only if those integrations are being tested — ask |

Passwords you generate yourself: the Postgres superuser password, the app database
password, and the Django secret key. Nobody else needs to know them.

## 0.4 Repo access

You will deploy the branch **`develop-backup-07-09-2026`**. You need read access to the
repository — either a deploy key on the box or a GitHub PAT.

Sanity-check that this directory is present on that branch before you begin:

```bash
git ls-tree --name-only origin/develop-backup-07-09-2026 deploy/
```

`deploy/ec2-all-in-one` should be listed. If it is not, the commit adding it has not been
pushed yet — ask the app team, and **do not hand-copy the files**. The compose file uses
paths relative to its own location and expects to sit exactly here inside the repo.

---

# Part A — AWS setup

## A.1 EC2 instance

**Launch: `t3.large` (2 vCPU / 8 GB RAM), Ubuntu 24.04 LTS, x86_64, 50 GB gp3, and leave
"T3 Unlimited" (unlimited CPU credits) ON — T3 launches that way by default.**

Why those numbers — measured against what this stack actually runs:

| Container | Steady RAM |
|---|---|
| `postgres` (also stores Temporal's whole event history) | 0.4–1.0 GB |
| `temporal` | 0.7–1.2 GB |
| `temporal-ui` | ~80 MB |
| `backend` | ~400 MB |
| `worker` (**launches AI subprocesses** for server-side jobs) | 0.5 GB idle, **+0.5–1.5 GB per active job** |
| `nginx` | ~15 MB |
| **Idle total** | **~2.2–2.7 GB** |
| **With one server-side job running** | **~3.5–4 GB** |

Plus one-off peaks of ~1.5–2 GB of RAM when compiling the frontend and building the backend
image.

- **8 GB is the floor.** `t3.medium` (4 GB) will run out of memory the first time a job runs
  while anything else is building.
- **Leave T3 Unlimited on.** T3 instances launch in `unlimited` mode by default, so this is
  usually a verification, not a change. It bills only for *surplus* CPU beyond what the
  instance has earned (~$0.05 per vCPU-hour), and an idle staging box accrues credits
  continuously — realistically cents per month, often zero. The alternative (`standard` mode)
  is free but throttles the box to 30% CPU once credits run out, turning a 20-minute build
  into an hour.
- **50 GB gp3, not the 8 GB default.** Measured baseline before any of your data:

  | Item | Size |
  |---|---|
  | Ubuntu + Docker | ~3 GB |
  | Backend image (`backend` and `worker` share these layers) | **3.3 GB** |
  | Postgres 621 MB + Temporal 620 MB + Temporal UI 159 MB + Node 231 MB + nginx 75 MB | ~1.7 GB |
  | Docker build cache (grows with every redeploy) | 1–3 GB |
  | Source 37 MB + `.git` 220 MB + frontend `node_modules` 329 MB | ~0.6 GB |
  | Swap file (Part B — it lives on this same volume) | 4 GB |
  | **Baseline** | **~14.5 GB** |

  30 GB boots and runs, but leaves little room as build cache accumulates and Postgres grows
  — **Temporal writes every workflow event into it**. 50 GB costs roughly $2/month more and
  removes the most likely cause of a mysterious staging outage. Growing a gp3 volume later is
  an online operation, but AWS enforces a **~6-hour cooldown** between modifications and you
  must extend the filesystem yourself (`growpart` + `resize2fs`), so it is not instant relief
  once you are already full. Run `docker system prune -af` monthly to keep the cache in check.
- **`t3.xlarge` (4 vCPU / 16 GB)** if more than 2–3 testers will be running jobs at once.
- **Cost note:** this is staging — **stop the instance when nobody is testing**. A stopped
  instance bills no compute, only the volume (~$4.50/mo) and the Elastic IP (~$3.60/mo; AWS
  bills all public IPv4). Running weekday business hours instead of 24/7 takes compute from
  ~$60/mo to ~$15/mo, which dwarfs any saving from a smaller disk. `t3a.large` (AMD) is ~10%
  cheaper for identical specs. **If you stop/start, the Elastic IP from §0.2 is what keeps the
  address stable** — without it, every restart requires a frontend rebuild.
- **The box needs outbound internet** (Docker Hub, npm, PyPI, GitHub, S3, the Anthropic API).
  A public subnet with an internet gateway, or a private subnet with a NAT gateway.

## A.2 Security group

Two inbound rules. That is all.

| Port | Source | Why |
|---|---|---|
| 22 | your admin IPs | SSH |
| 80 | the IPs from §0.2 | the app **and** its API — developers' companions poll this same port |

**Do not open 5432, 7233, 8080.** The compose file binds them to `127.0.0.1`, so they are not
exposed even if someone loosens the group. Reach them over an SSH tunnel:

```bash
ssh -i key.pem -L 8080:localhost:8080 -L 5433:localhost:5433 ubuntu@<ec2-ip>
```

Temporal UI is then `http://localhost:8080`; Postgres is `localhost:5433`.

There is **no TLS** in this setup (see §E.2). Port 80 must stay restricted to known IPs or a
VPN.

## A.3 S3 bucket and IAM

Create a **new, dedicated, fully private** bucket — do not reuse another application's.
Default settings are correct: Block Public Access ON, no static hosting, **no CORS
configuration needed**. The app never gives a browser a link to the bucket; it reads files
server-side and serves them through its own API.

Then pick one of two credential paths.

### Option 1 — instance role (recommended, no secrets on disk)

Create an IAM role for EC2 with this policy, and attach it to the instance:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BucketList",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::<bucket-name>"
    },
    {
      "Sid": "ObjectAccess",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::<bucket-name>/*"
    }
  ]
}
```

Then leave `S3_ACCESS_KEY` and `S3_SECRET_KEY` **blank** in `.env`.

⚠️ **The one gotcha that will cost you an afternoon:** the app runs inside Docker, and a
container reaching instance metadata is one extra network hop. EC2 defaults the metadata hop
limit to 1, which **silently blocks containers from using the instance role**. Raise it to 2:

```bash
aws ec2 modify-instance-metadata-options --instance-id <id> --http-put-response-hop-limit 2 --http-tokens required
```

Symptom if you skip it: the app starts fine, then every file operation fails with
`NoCredentialsError`.

### Option 2 — IAM user access key

Create an IAM user with the same policy, generate an access key, and put it in
`S3_ACCESS_KEY` / `S3_SECRET_KEY`. Simpler, but the secret now lives on the box.

---

# Part B — Prepare the box

## ⚠️ What you install here — and what you must NOT

**You install exactly three packages: `docker.io`, `docker-compose-v2`, `git`** (plus a swap
file). That is the entire operating-system setup.

**Do NOT install Postgres, nginx, Temporal, Python, Node, or any application dependency on
the box.** They all run as containers and are handled by `docker compose up` in Part D.

This is the most likely way an experienced engineer breaks this deployment, precisely because
installing them is normally the right instinct. `apt install postgresql` gives you a native
Postgres holding port **5432**, and `apt install nginx` a native nginx holding port **80** —
both then fight the containers for the same ports. The symptoms (connection refused, or the
default nginx welcome page instead of the app) point nowhere near the cause.

If you have already installed either one, remove it or stop and disable it before continuing:

```bash
sudo systemctl disable --now nginx postgresql 2>/dev/null; true
```

## B.1 Install Docker and git

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
```

Log out and back in for the group change to apply.

## B.2 Add swap

Add swap — it costs nothing and
turns a build-time out-of-memory kill into a merely slow build:

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

# Part C — Get the code and configure it

## C.1 Clone the branch

```bash
git clone -b develop-backup-07-09-2026 <repo-url> ~/AI-First-SDLC-App
cd ~/AI-First-SDLC-App
git rev-parse --abbrev-ref HEAD
```

That last command must print `develop-backup-07-09-2026`.

## C.2 Create the config file

```bash
cp deploy/ec2-all-in-one/.env.ec2.example .env
chmod 600 .env
```

Now edit `.env` and replace every `<...>` placeholder. **It must be at the repo root and
named exactly `.env`** — that is the only file the app and Docker read. (There is a
`backend/.env` in some checkouts; it is a leftover that nothing loads. Ignore it.)

**The four that fail in confusing ways if you get them wrong:**

| Setting | Must be | If wrong |
|---|---|---|
| `VITE_API_BASE` | `http://<your-address>/api` | Every developer is handed a connection command pointing at **their own laptop**, and it silently never connects. |
| `DJANGO_ALLOWED_HOSTS` | your address, **bare** — no `http://`, no port | Every single request fails with a 400 error. |
| `CSRF_TRUSTED_ORIGINS` | your address **with** `http://` | Login appears to work, then every action fails with a 403. |
| `DATABASE_URL` | the `sdlc_app` user, **never** `postgres` | Silently disables this app's tenant data isolation. Non-negotiable. |

Yes, two of those want the address *with* the scheme and one *without*. That is Django's
convention, not a typo.

---

# Part D — Deploy

## D.1 Start everything

Run from the repo root. (The compose file resolves its paths relative to its own location.)

```bash
export COMPOSE_FILE=deploy/ec2-all-in-one/docker-compose.ec2.yml
```

```bash
docker compose up -d --build
```

First run takes 10–20 minutes: it builds a Python image and compiles the frontend.

**`frontend-build` will show as `Exited (0)`. That is correct, not a failure** — it compiles
the app and stops. nginx waits for it to finish before starting.

## D.2 Create the database schema (once)

The app normally connects as a limited user that deliberately **cannot** change the database
structure. Setting up the structure — and creating that limited user in the first place —
needs the superuser, so override the connection for this one command:

```bash
docker compose run --rm -e DATABASE_URL="postgres://postgres:<superuser-pw>@postgres:5432/sdlc_platform" backend python manage.py migrate
```

Then load starter data as the normal user:

```bash
docker compose run --rm backend python manage.py seed_demo
```

**Save the output** — it prints a tenant ID, a project ID, and a demo login. The app team
needs these. Real users sign themselves up through the web app afterwards.

```bash
docker compose restart backend worker
```

## D.3 One required Temporal setting

```bash
docker compose exec temporal grep workerVersioning /etc/temporal/config/dynamicconfig/development-sql.yaml
```

You must see **both** `frontend.workerVersioningDataAPIs` and
`frontend.workerVersioningWorkflowAPIs`. Both are needed; one alone does nothing. They are
already in the repo file that this compose mounts, so this is a verification step, not a
change. Temporal reads that file on its own — no restart.

Why it matters: without it, a `worker` running outdated code can pick up jobs, do less than
it should, and **report success**. The app team hit this in production once; there is an
incident document about it.

---

# Part E — Verify, then hand over

## E.1 Acceptance checklist

You are done when all seven pass. No app knowledge needed for any of them.

```bash
docker compose ps
```

- [ ] **1.** Six containers `Up` — `postgres`, `temporal`, `temporal-ui`, `backend`, `worker`,
      `nginx` — while `frontend-build` shows `Exited (0)`, and `temporal` is **not**
      `Restarting`.
- [ ] **2.** `curl -I http://<address>/` returns `200`.
- [ ] **3.** `curl -s http://<address>/api/auth/me/` returns **JSON** (a 401/403 body is the
      correct answer here — it proves the API proxy works).
- [ ] **4.** `docker compose logs --tail 30 worker` shows it connected to Temporal and
      polling. **Do not skip this** — the app looks fine while the worker is dead.
- [ ] **5.** In a browser at `http://<address>`, the page loads and you can log in with the
      demo account from §D.2.
- [ ] **6.** **The S3 check.** Log in, go to the **Connect Machine** screen, and confirm the
      command shown contains **your EC2 address**, not `localhost`. Then ask the app team to
      run any action that produces a file, and confirm objects appear in the bucket:
      `aws s3 ls s3://<bucket-name>/ --recursive | head`. This is the only step that proves
      the S3 credentials and the metadata hop limit are right.
- [ ] **7.** Temporal UI loads through the SSH tunnel from §A.2 at `http://localhost:8080`.

## E.2 Known limitations — state these when you hand over

- **No HTTPS.** Passwords and access tokens cross the network in the clear. Acceptable only
  because port 80 is IP-restricted. To add TLS later: put an ALB or Caddy in front, then
  update `VITE_API_BASE`, `CSRF_TRUSTED_ORIGINS`, and every developer's connection command
  to `https://` — and **rebuild the frontend**.
- **The admin pages look unstyled.** Expected. The app does not package its admin stylesheets
  for production and `DJANGO_DEBUG=false` (the safe setting) does not serve them. The API and
  the main app are unaffected. Fixing it needs an application code change, not a config one.
- **One box, no redundancy.** A restart interrupts running jobs.
- **Secrets live in `.env` on the box.** `chmod 600`, and rotate anything that was ever
  pasted into chat.

## E.3 Routine operations

Redeploy after the app team pushes a change:

```bash
cd ~/AI-First-SDLC-App && git pull
```

```bash
docker compose up -d --build backend worker
```

```bash
docker compose run --rm frontend-build && docker compose restart nginx
```

If they say the database structure changed, re-run the `migrate` command from §D.2 first.
**Any time the public address changes, you must rebuild the frontend** — restarting is not
enough, the address is compiled in.

Back up: the `pgdata` Docker volume (all application data) and the S3 bucket (all files).
`.env` is not reproducible — keep a copy in your secret store.

---

# Part F — For the app team, not DevOps

Some developers run a **"companion"** on their own laptop: a small program that lets the
platform run AI coding jobs against their local code checkout. **This requires nothing from
you** — no inbound ports, no VPN, no firewall changes. The companion only makes **outbound**
calls to port 80 on this box, the same port a browser uses.

Pass this to the developers verbatim:

> The platform is now at `http://<address>`. Log in, open **Connect Machine**, generate a
> token, and copy the command it shows — it already points at the server. On your laptop you
> need: a clone of this repo, a **dedicated** Python 3.12 virtualenv with
> `backend/requirements.txt` installed (a shared/global Python gets `anyio` downgraded by
> other projects and the companion then refuses to start), the `claude` CLI installed and
> signed in, and a local clone of whichever repo you're building. Then run the copied command
> with `--repo-path <your-clone> --worktrees ~/sdlc` appended. The screen flips to
> **● Connected** within about 30 seconds.

---

# Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Every request returns 400 / "Invalid HTTP_HOST" | The address is missing from `DJANGO_ALLOWED_HOSTS`. Bare host — no scheme, no port. |
| Connect Machine shows `--api-url http://localhost:8000` | `VITE_API_BASE` was wrong when the frontend was compiled. Fix `.env`, then `docker compose run --rm frontend-build && docker compose restart nginx`. |
| Login works, then everything returns 403 | The origin is missing from `CSRF_TRUSTED_ORIGINS` — it needs the scheme (`http://1.2.3.4`). |
| File operations fail with `NoCredentialsError` | Instance-role metadata is blocked by the Docker hop. Apply the hop-limit fix in §A.3. |
| File operations fail with `AccessDenied` or `NoSuchBucket` | Bucket name, region, or IAM policy. `S3_REGION` must be the bucket's actual region. |
| UI works but nothing ever progresses | The `worker` container. `docker compose logs worker`. |
| `worker` logs `STANDING DOWN` and exits | Working as designed: newer code owns the job queue. Fix is `git pull` + rebuild, not a restart. |
| `temporal` restarting, log says `development-sql.yaml: no such file` | You ran compose from the wrong directory. Run it from the repo root. |
| A companion connects but a job never finishes; nginx logs a 504 | Someone shortened `proxy_read_timeout` in `nginx.conf`. It is 960s **on purpose** — the client's own limit is 900s, and a proxy that gives up first once caused an audit to be closed twice and 1,065 records discarded. |
| 413 when uploading a document | Raise `client_max_body_size` in `nginx.conf` (200 MB by default). |
| Box crawls after a build | CPU credits exhausted. Enable T3 Unlimited. |
| `docker compose` says a variable is missing on `ps`/`logs` | Compose validates the whole file on every subcommand. You are in the wrong directory or `.env` is incomplete. |
