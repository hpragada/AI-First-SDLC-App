# Shared AWS environment — runbook

Goal: two developers share one **live** platform state (DB + object store + workflows),
so whatever one does the other can continue, and neither laptop needs to be on.

We reuse the team's existing AWS: the **shared EC2 Postgres** and **S3**. We add only
**Temporal**. No app code changes — Django reads every endpoint from `.env`.

```
Dev A laptop ─┐            ┌── EC2 Postgres  (db: sdlc_platform, isolated)
  app tier    ├─ network ──┼── Temporal (on EC2)  ← the only new piece
Dev B laptop ─┘            └── AWS S3   (bucket: sdlc-artifacts-*)
  app tier                     (each dev runs backend+worker+frontend locally)
```

Files here:
- `bootstrap_shared_db.sql` — one-time DB/role/extension setup (run as superuser).
- `docker-compose.temporal.yml` — Temporal + UI on EC2, backed by the existing Postgres.
- `.env.shared.example` — the per-developer env template.

---

## Prerequisites (verify BEFORE starting — plan flagged these)
1. **pgvector installable** on the EC2 Postgres for its major version
   (`apt install postgresql-16-pgvector` or build from source). The app requires the
   `vector` extension; only a superuser can create it (done once in the SQL script).
2. **Memory headroom** on the t3.large (8 GB, shared) for Temporal. If it's tight,
   use **Temporal Cloud** (Option T2) instead and skip `docker-compose.temporal.yml`.
3. **Network reachability**: both dev laptops can reach the EC2 Postgres (5432), Temporal
   gRPC (7233), and the Temporal UI (8080). Prefer a security group scoped to the devs'
   IPs, or Tailscale on the EC2 box. **Never** open 5432/7233/8080 to `0.0.0.0/0`.
   S3 needs nothing opened (IAM).

---

## Step 1 — One-time: isolate a database on the shared Postgres
Run as a **superuser** (postgres / rds_superuser). Edit the passwords in the file first.

```bash
psql "postgres://<superuser>:<pw>@<pg-host>:5432/postgres" -f bootstrap_shared_db.sql
```
This creates: db `sdlc_platform` (owned by a new **`sdlc_migrator`** role with `CREATEROLE`),
the `vector` extension inside it, and the `temporal` / `temporal_visibility` databases.
It does **not** create `sdlc_app` — the migrations do that (Step 3).

## Step 2 — One-time: dedicated S3 bucket
Create a bucket (e.g. `sdlc-artifacts-shared`) in your region, and an IAM user/policy
scoped to just that bucket (`s3:GetObject/PutObject/ListBucket/DeleteObject`). Note the
access key + secret (or plan to use an instance role). Do **not** reuse another app's bucket.

## Step 3 — One-time: run migrations + seed against the shared DB
From one machine, with `.env` filled from `.env.shared.example`. Migrations need the
**privileged** role, so override `DATABASE_URL` to `sdlc_migrator` just for this command
(day-to-day the app uses the `sdlc_app` role from `.env`). `--no-deps` stops Compose from
spinning up a local Postgres:

```bash
# migrate as the migration role (creates sdlc_app + RLS policies + all tables)
docker compose --profile app run --rm --no-deps \
  -e DATABASE_URL="postgres://sdlc_migrator:<mig-pw>@<pg-host>:5432/sdlc_platform" \
  backend python manage.py migrate

# seed demo data as the normal app role (uses DATABASE_URL from .env)
docker compose --profile app run --rm --no-deps backend python manage.py seed_demo
```
`seed_demo` prints a **`tenant_id`** — share it with both devs (they paste it into the
UI's `X-Tenant-ID`). Run Step 3 **once total**, not per developer.

> Windows: `./make.ps1` doesn't take the override, so use the raw `docker compose` commands above.

## Step 4 — Temporal (choose T1 or T2)
Temporal is a durable-workflow engine (agent runs are Temporal workflows). It's the
only always-on infra piece we add; it stores its state in the `temporal` /
`temporal_visibility` databases already created on the EC2 Postgres.

**T1 — self-host on EC2** (recommended if the box has RAM). Runs Temporal + UI as two
Docker containers on the EC2 box, using **host networking** so they reach the native
Postgres at `127.0.0.1:5432`, connecting as `sdlc_migrator` (which owns those DBs).
`SKIP_DB_CREATE=true` (set in the compose) tells Temporal the DBs already exist — it
just installs its schema.

Detailed steps (Ubuntu EC2, no Docker yet). Terms used below: `<ec2-public-ip>` is what
your browser/devs reach; `<ec2-private-ip>` is the VPC-internal IP Temporal binds to
under host networking (find it: `hostname -I | awk '{print $1}'`, e.g. `172.31.13.79`).

```bash
# 4a) Install Docker + the compose plugin (once)
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker

# 4b) Put the files on the box. Create the dirs FIRST (scp won't make them), and copy the
#     dynamicconfig FILE (not the folder — `scp -r` nests it and Temporal won't find it).
#   From your laptop:
#     ssh -i key.pem ubuntu@<ec2-public-ip> "mkdir -p ~/temporal/dynamicconfig"
#     scp -i key.pem deploy/shared-aws/docker-compose.temporal.yml ubuntu@<ec2-public-ip>:~/temporal/
#     scp -i key.pem docker/temporal/dynamicconfig/development-sql.yaml ubuntu@<ec2-public-ip>:~/temporal/dynamicconfig/
#   Verify on the box:  ls -la ~/temporal/dynamicconfig/   → development-sql.yaml directly inside (no nested dir)

# 4c) Let containers on 127.0.0.1 authenticate to Postgres as sdlc_migrator.
#     Add to pg_hba.conf (path: sudo -u postgres psql -c "SHOW hba_file;"):
#       host  temporal             sdlc_migrator  127.0.0.1/32  scram-sha-256
#       host  temporal_visibility  sdlc_migrator  127.0.0.1/32  scram-sha-256
#     then:  sudo systemctl reload postgresql

# 4d) Create ~/temporal/.env so every compose command has the vars (MIG_PW is required by
#     ALL subcommands — ps/logs/up — not just up). TEMPORAL_UI_ADDR MUST be the PRIVATE IP,
#     because under host networking Temporal binds gRPC to the private IP, not 127.0.0.1 —
#     the UI dials this or you get a 500 (namespaces/cluster-info → 503).
cd ~/temporal
cat > .env <<EOF
MIG_PW=<sdlc_migrator-password>
TEMPORAL_UI_ADDR=<ec2-private-ip>:7233
TEMPORAL_UI_CORS=http://<ec2-public-ip>:8080
EOF
chmod 600 .env

# 4e) Start Temporal (reads ~/temporal/.env automatically)
sudo docker compose -f docker-compose.temporal.yml up -d

# 4f) Verify
sudo docker compose -f docker-compose.temporal.yml ps            # both "Up" (temporal not "Restarting")
sudo docker compose -f docker-compose.temporal.yml logs --tail 20 temporal      # matching-engine polling = healthy
sudo docker compose -f docker-compose.temporal.yml logs --tail 10 temporal-ui   # namespaces/cluster-info → 200
```

**4g) REQUIRED — turn on worker versioning.** Temporal ships this switched off, and without it a
worker running stale code can still take work off the queue, do less than the current code would
and report success (this is exactly what `docs/INCIDENT_2026-08-26_stale_worker.md` is about).
The repo's `docker/temporal/dynamicconfig/development-sql.yaml` already carries both flags, so
copying it in Step 4b is enough — verify they arrived:

```bash
grep workerVersioning ~/temporal/dynamicconfig/development-sql.yaml
#   frontend.workerVersioningDataAPIs:       <- the build-ID registry APIs
#   frontend.workerVersioningWorkflowAPIs:   <- lets task dispatch honour a build ID
```

Both are needed; one alone does nothing. **No restart** — Temporal re-reads that file on its own
(measured: ~12s), so this is a zero-downtime change you can make with work in flight. Until the
flags are on, workers log that versioning is off and behave exactly as they did before.

Open **7233** (workers) and **8080** (UI) in the security group to the devs' IPs. UI at
`http://<ec2-public-ip>:8080` (shows the `default` namespace). Each dev sets
`TEMPORAL_HOST=<ec2-public-ip>:7233` in `.env` — AWS NAT forwards that to the private IP
where Temporal listens, so workers connect fine.

**T2 — Temporal Cloud**. Skip the compose file; set `TEMPORAL_HOST` to the Cloud
endpoint + namespace and add mTLS certs in `.env`.

## Step 5 — Each developer runs the app tier locally (pointed at AWS)
Each dev copies `.env.shared.example` → **`AI-First-SDLC-App/.env`** (the repo-root file —
that's the only one Django and Compose read; `backend/.env` is a leftover and is NOT
loaded, so don't bother with it), fills the shared values, then starts ONLY the app
services (`--no-deps` keeps local postgres/minio/temporal down):

```bash
docker compose --profile app up --no-deps backend worker frontend
```
Open the frontend (`http://localhost:5173`), set `X-Tenant-ID` to the shared `tenant_id`.
Both devs now read/write the same DB, S3 bucket, and Temporal — live.

---

## Verify it's actually shared
1. Dev A creates/changes a WorkItem under the shared `tenant_id`.
2. Dev B (same `tenant_id`) refreshes and sees it; Dev B advances it (gate / artifact).
3. Dev A refreshes → sees Dev B's change. ✅ live shared DB.
4. An artifact body uploaded by one dev is retrievable by the other (check the S3 bucket).
5. A workflow started by one dev shows in the Temporal UI for both.

## Gotchas
- **Migrations = `sdlc_migrator`, runtime = `sdlc_app`.** Only ever pass the migrator DSN
  for `migrate`. Keep `POSTGRES_APP_PASSWORD` in `.env` equal to the `sdlc_app` password
  the migration created.
- **Only the repo-root `.env` is used.** `backend/.env` is a leftover the code never reads
  (settings loads `BASE_DIR.parent/.env`; compose uses the root `.env`). Edit the root one.
- **Two workers, one task queue** is fine, and since worker versioning (Step 4g) the platform
  *enforces* what used to be an instruction to "keep code roughly in sync": only the newest code
  may serve a queue. Two devs on the **same commit** both keep serving — they are recognised as
  one build by content, not by file dates, so neither evicts the other. A worker on **older** code
  logs `STANDING DOWN` and exits without taking a single task; work already in its hands finishes
  first. So a stale worker can no longer quietly do the older thing to somebody's run — but it
  also means that if your worker exits on startup, the queue is owned by newer code and the fix
  is `git pull`, not a restart.
- **Secrets**: the real `.env` must stay out of git (already `.gitignore`d). Rotate the
  dev-default passwords; scope the IAM policy to the one bucket.

## Troubleshooting Temporal (issues we actually hit)
- **`ps`/`logs` error: `required variable MIG_PW is missing`** — Compose validates every
  service's env on *any* subcommand. Put `MIG_PW` (and `TEMPORAL_UI_ADDR`, `TEMPORAL_UI_CORS`)
  in `~/temporal/.env`; then no inline vars are needed.
- **temporal container `Restarting`, log: `dynamicconfig/development-sql.yaml: no such file`** —
  the mounted `./dynamicconfig` folder doesn't contain the file (usually because `scp -r`
  nested it as `dynamicconfig/dynamicconfig/…`). Ensure `~/temporal/dynamicconfig/development-sql.yaml`
  exists directly, then `up -d --force-recreate`.
- **UI shows 500; `/api/v1/namespaces` and `/cluster-info` → 503** — the UI can't reach the
  Temporal gRPC server. Under host networking Temporal binds to the **private IP** (see the
  startup log line `Temporal CLI address: <private-ip>:7233`), not `127.0.0.1`. Set
  `TEMPORAL_UI_ADDR=<private-ip>:7233` in `~/temporal/.env` and recreate `temporal-ui`.
- **Worker on a laptop can't connect to `<public-ip>:7233`** — open 7233 in the security
  group to that IP. Temporal listening on the private IP is fine; AWS NAT forwards the public IP.
