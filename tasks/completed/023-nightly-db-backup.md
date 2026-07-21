---
id: 023
title: Nightly Postgres backup to S3
status: done
stage: qa
owner: eng-executor
created: 2026-07-21
dependencies: []
links: [scripts/backup-db.sh, scripts/deploy-server.sh, .github/workflows/deploy.yml]
---

# 023 — Nightly Postgres backup to S3

## Objective
All production user data lives in a single Docker volume (`pgdata`) on one
t3.small EC2 instance with no backup of any kind — a disk failure loses
everything. Add a nightly `pg_dump` → S3 so the database is recoverable.

## User stories
- As the founder, I want an automatic nightly database backup off the EC2 box
  so that a disk/instance failure cannot destroy user data.

## Acceptance criteria
- [x] A nightly cron on the EC2 box dumps `founder_os` and uploads it to S3.
- [x] The dump is restorable (`pg_dump -Fc` → `pg_restore`).
- [x] Safe to ship before AWS setup: with no bucket configured the job no-ops
      cleanly (exit 0, logged notice) — deploys are never blocked.
- [x] Bucket name flows through the existing GitHub-secret → server-.env sync
      (`BACKUP_S3_BUCKET`), same pattern as the other deploy secrets.
- [x] Retention handled by S3 lifecycle (30-day expiry), not script logic.

## Success metrics
- `/var/log/founder-os-db-backup.log` shows a nightly `OK: uploaded …` line and
  objects appear under `s3://<bucket>/postgres/`.

## Out of scope
- Alembic-aware point-in-time recovery / WAL archiving.
- Backing up Redis (cache + broker only) or the n8n volume.
- Automated restore drills.

## Requirements / open questions
- One-time AWS setup is the founder's (documented in the `backup-db.sh`
  header): create private bucket in ap-south-1 + lifecycle rule, grant the EC2
  instance role `s3:PutObject` on `postgres/*`, add repo secret
  `BACKUP_S3_BUCKET`, re-run Deploy.

---

## Architecture
- Data model + Alembic: none — ops only, no product code touched.
- API: none.
- File placement / components reused: `scripts/backup-db.sh` (new, runs on the
  box); `scripts/deploy-server.sh` installs `/etc/cron.d/founder-os-db-backup`
  idempotently on every deploy and reuses `sync_env`/`patch_var` for the bucket
  name; `.github/workflows/deploy.yml` passes the new optional secret.
- Integration points: cron (22:00 UTC = 03:30 IST), Docker (`docker exec
  founder-os-postgres pg_dump`), S3 via the instance role (no new credentials).
- Risks / trade-offs: logical dump, not PITR — up to 24 h of data loss is
  accepted; `aws` CLI auto-installed via snap best-effort (deploy warns, never
  fails, if unavailable); IAM grants PutObject only so the box cannot read or
  delete existing backups if compromised.

## Build notes
- Changed files: `scripts/backup-db.sh` (new), `scripts/deploy-server.sh`,
  `.github/workflows/deploy.yml`.
- How verified: see QA results.

## Review findings
- [fixed] scripts/backup-db.sh — under `set -euo pipefail` a no-match `grep`
  killed the script (exit 1) before the skip notice; `|| true` on the pipeline.
- Verdict: Pass.

## QA results
- Commands (local, against the dev `founder-os-postgres` container +
  a stubbed `aws` on PATH):
  - `bash -n` both scripts → OK.
  - No-bucket path → logged skip notice, exit 0.
  - Full path → real `pg_dump -Fc` (1.0 MB, `PGDMP` magic), upload invoked,
    temp file removed by trap.
  - Restore drill → `pg_restore` into a throwaway `restore_test` DB: 45 tables
    restored, equal to the 45 in the source `founder_os`; no errors.
- Pass. (Not verified live on EC2 — first real run happens the night after the
  AWS one-time setup + deploy; check the log line above.)

## Security report
- Bucket name is non-secret but flows through the charset-validated
  `patch_var` path; no secrets echoed; bucket private + PutObject-only role;
  dump never leaves the box unencrypted-in-public (private bucket, SSE-S3
  default). Verdict: Pass.
