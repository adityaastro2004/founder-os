#!/usr/bin/env bash
# On-server deploy for the Founder OS backend.
# Invoked by .github/workflows/deploy.yml via SSM RunCommand (runs as root);
# the caller has already reset the checkout to origin/main and passes the
# previous HEAD sha for rollback.
#
# Server model (EC2, ap-south-1):
#   /home/ubuntu/founder-os              git checkout
#   postgres + redis                     docker compose (localhost-only)
#   founder-api / founder-celery         systemd units, venv at apps/api/.venv
#   nightly DB backup → S3               /etc/cron.d/founder-os-db-backup (scripts/backup-db.sh)
#
# Rollback restores the previous code but NOT the schema: alembic downgrades
# are manual by design, so migrations must stay backward-compatible for at
# least one release.
set -euo pipefail

REPO=/home/ubuntu/founder-os
API=$REPO/founder-os/apps/api
PREV=${1:?usage: deploy-server.sh <rollback-sha>}

install_deps() {
  sudo -u ubuntu bash -c "cd $API && source .venv/bin/activate && pip install -q -r requirements.txt"
}

# Sync selected secrets from the caller's environment into the server .env.
# The workflow passes them as FOS_-prefixed vars sourced from GitHub Actions
# secrets — rotate a key there and the next deploy applies it. Values are
# never echoed; empty/unset vars are skipped so old deploys stay compatible.
# Runs before install/migrate/restart so a refused value aborts with the box
# untouched. Values are restricted to a safe charset because they pass through
# sed and an unquoted env assignment — anything else is refused, not written.
# ':' and '/' are allowed for URL values (redirect URIs); both are inert in the
# '|'-delimited sed and in an unquoted assignment.
sync_env() {
  local envfile=$API/.env synced=""
  [ -f "$envfile" ] || sudo -u ubuntu install -m 600 /dev/null "$envfile"
  patch_var() {
    local name=$1 value=$2
    [ -n "$value" ] || return 0
    if ! [[ "$value" =~ ^[A-Za-z0-9._:/-]+$ ]]; then
      echo "sync_env: refusing ${name}: unexpected characters in value" >&2
      return 1
    fi
    if sudo -u ubuntu grep -q "^${name}=" "$envfile"; then
      sudo -u ubuntu sed -i "s|^${name}=.*|${name}=${value}|" "$envfile"
    else
      printf '%s=%s\n' "$name" "$value" | sudo -u ubuntu tee -a "$envfile" >/dev/null
    fi
    synced="$synced $name"
  }
  # Pin the runtime to production posture. This is the authoritative gate for
  # the dev-only x-test-user auth bypass + unauthenticated test routes (app/
  # auth.py, app/main.py): they are LIVE whenever APP_ENV != production, so a
  # fresh/empty server .env must never be left at the development default.
  patch_var APP_ENV "production"
  patch_var DEBUG "false"
  patch_var OPENAI_API_KEY "${FOS_OPENAI_API_KEY:-}"
  patch_var GEMINI_API_KEY "${FOS_GEMINI_API_KEY:-}"
  patch_var GOOGLE_CLIENT_ID "${FOS_GOOGLE_CLIENT_ID:-}"
  patch_var GOOGLE_CLIENT_SECRET "${FOS_GOOGLE_CLIENT_SECRET:-}"
  patch_var GOOGLE_REDIRECT_URI "${FOS_GOOGLE_REDIRECT_URI:-}"
  patch_var OAUTH_STATE_SECRET "${FOS_OAUTH_STATE_SECRET:-}"
  patch_var BACKUP_S3_BUCKET "${FOS_BACKUP_S3_BUCKET:-}"
  if [ -n "$synced" ]; then echo "env synced:$synced"; fi
}

migrate() {
  sudo -u ubuntu bash -c "cd $API && source .venv/bin/activate && alembic upgrade head"
}

# Install the nightly DB backup cron (scripts/backup-db.sh → S3). Idempotent:
# rewrites the cron entry every deploy. The script itself no-ops until the
# BACKUP_S3_BUCKET secret is set, and a missing aws CLI only warns here so a
# broken snap store can never block a deploy.
install_backup() {
  chmod +x "$REPO/scripts/backup-db.sh"
  cat > /etc/cron.d/founder-os-db-backup <<CRON
# Managed by deploy-server.sh — edits are overwritten on every deploy.
# Nightly Postgres dump → S3 at 22:00 UTC (03:30 IST).
30 22 * * * root $REPO/scripts/backup-db.sh >> /var/log/founder-os-db-backup.log 2>&1
CRON
  chmod 644 /etc/cron.d/founder-os-db-backup
  if ! command -v aws >/dev/null 2>&1; then
    snap install aws-cli --classic >/dev/null 2>&1 \
      || echo "WARN: aws CLI unavailable — nightly DB backup will fail until installed" >&2
  fi
}

restart_and_check() {
  systemctl restart founder-api founder-celery
  for _ in $(seq 1 12); do
    sleep 5
    if curl -fsS -o /dev/null http://127.0.0.1:8000/; then
      return 0
    fi
  done
  return 1
}

sync_env
install_deps
migrate
install_backup
if restart_and_check; then
  echo "DEPLOY OK: now at $(sudo -u ubuntu git -C "$REPO" rev-parse --short HEAD)"
  exit 0
fi

echo "HEALTH CHECK FAILED — rolling back to $PREV" >&2
sudo -u ubuntu git -C "$REPO" reset -q --hard "$PREV"
install_deps || true
if restart_and_check; then
  echo "Rolled back to $PREV — deploy FAILED but service restored" >&2
else
  echo "CRITICAL: rollback also unhealthy — manual intervention required" >&2
fi
exit 1
