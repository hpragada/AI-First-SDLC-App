# ADR 0001 — Object store: MinIO local, AWS S3 in production

- **Status:** Accepted (2026-06-22)
- **Deciders:** Build team
- **Context task:** raised during P0-T2; affects the storage layer built in P0-T5/T8.

## Decision
Use a **single, provider-agnostic S3 access path** (boto3 + `S3_ENDPOINT_URL`):
- **Local dev / CI:** MinIO (S3-compatible) via Docker Compose — `S3_ENDPOINT_URL` set.
- **Production / cloud:** AWS S3 (or the client's managed S3) — `S3_ENDPOINT_URL` empty,
  credentials via IAM role / instance profile, not static keys.

MinIO is **not** the production store; it is the local emulator of the same S3 API.

## Why (and why not "switch to AWS S3 now")
- CLAUDE.md already specifies "S3-compatible (MinIO locally)." AWS S3 and MinIO speak the
  **same API**, so the choice is configuration (endpoint + credentials), not architecture.
- We store **pointers** (`s3_key`, `content_hash`, version) in Postgres, never bodies
  (non-negotiables #1, #3) — so there is **no lock-in** to a specific object-store vendor
  and no migration cost that grows over time.
- "MinIO is open source → may be insecure" is a misconception: open source ≠ insecure, and
  for local dev MinIO is a container on the dev machine, not an internet-facing surface.
  Real security hardening (sandbox, egress allowlist, secrets vault) is **Phase 5**.
- Forcing real AWS S3 into local dev would require AWS creds + bucket + IAM for every dev
  and CI, add cost, remove offline development, and pull a **cloud dependency into Phase 0**,
  which the Phase 0 spec lists as out of scope (managed cloud stores are **Phase 5**).

## Consequences
- The P0-T5/T8 storage module reads `S3_ENDPOINT_URL` (optional). Unset → AWS S3 defaults.
- A staging/shared environment can point at a real S3 bucket with **only env changes**.
- Production object-store provisioning is finalized in the Phase 5 cloud migration.
