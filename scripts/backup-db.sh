#!/usr/bin/env bash
# Nightly Postgres backup → S3 for the Founder OS production box.
#
# Installed by scripts/deploy-server.sh as /etc/cron.d/founder-os-db-backup
# (daily 22:00 UTC = 03:30 IST, as root). Logs to /var/log/founder-os-db-backup.log.
#
# Reads BACKUP_S3_BUCKET from the API .env — deploy-server.sh syncs it there
# from the GitHub Actions secret of the same name. Until that secret is set
# the script logs a notice and exits 0, so this is safe to ship before the
# bucket exists.
#
# One-time AWS setup (console or CloudShell, region ap-south-1):
#   1. Create a private bucket:
#        aws s3api create-bucket --bucket <name> --region ap-south-1 \
#          --create-bucket-configuration LocationConstraint=ap-south-1
#        aws s3api put-public-access-block --bucket <name> \
#          --public-access-block-configuration \
#          BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
#   2. Expire backups after 30 days:
#        aws s3api put-bucket-lifecycle-configuration --bucket <name> \
#          --lifecycle-configuration '{"Rules":[{"ID":"expire-old-backups",
#          "Status":"Enabled","Filter":{"Prefix":"postgres/"},
#          "Expiration":{"Days":30}}]}'
#   3. Let the EC2 instance role write (only write) to the prefix:
#        aws iam put-role-policy --role-name <instance-role> \
#          --policy-name founder-os-db-backup --policy-document \
#          '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
#          "Action":"s3:PutObject","Resource":"arn:aws:s3:::<name>/postgres/*"}]}'
#   4. Add repo secret BACKUP_S3_BUCKET=<name>, then re-run the Deploy workflow.
#
# Restore (on the box):
#   aws s3 cp s3://<bucket>/postgres/<file>.dump /tmp/restore.dump
#   docker cp /tmp/restore.dump founder-os-postgres:/tmp/restore.dump
#   docker exec founder-os-postgres pg_restore -U founder -d founder_os \
#     --clean --if-exists /tmp/restore.dump
set -euo pipefail

# Overridable for local testing; defaults match the EC2 server model
# documented in deploy-server.sh (git root at /home/ubuntu/founder-os,
# monorepo nested one level down).
ENV_FILE=${ENV_FILE:-/home/ubuntu/founder-os/founder-os/apps/api/.env}
CONTAINER=${CONTAINER:-founder-os-postgres}
DB_USER=${DB_USER:-founder}
DB_NAME=${DB_NAME:-founder_os}

log() { echo "[$(date -u +%FT%TZ)] $*"; }

# `|| true`: under pipefail a no-match grep would otherwise kill the script
# (set -e) before it can log the skip notice.
BUCKET=$(grep -s '^BACKUP_S3_BUCKET=' "$ENV_FILE" | tail -1 | cut -d= -f2- || true)
if [ -z "$BUCKET" ]; then
  log "BACKUP_S3_BUCKET not set in $ENV_FILE — skipping backup (set the repo secret and redeploy)"
  exit 0
fi

command -v aws >/dev/null 2>&1 || { log "ERROR: aws CLI not installed"; exit 1; }
docker ps --format '{{.Names}}' | grep -qx "$CONTAINER" \
  || { log "ERROR: container $CONTAINER not running"; exit 1; }

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TMP=$(mktemp /tmp/founder_os_backup.XXXXXX)
trap 'rm -f "$TMP"' EXIT

# Custom-format dump (-Fc): compressed, restorable table-by-table via pg_restore.
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$TMP"

SIZE=$(du -h "$TMP" | cut -f1)
KEY="postgres/${DB_NAME}_${STAMP}.dump"
aws s3 cp --only-show-errors "$TMP" "s3://${BUCKET}/${KEY}"
log "OK: uploaded ${KEY} (${SIZE}) to s3://${BUCKET}"
