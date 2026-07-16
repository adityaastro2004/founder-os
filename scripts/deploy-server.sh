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
sync_env() {
  local envfile=$API/.env synced=""
  [ -f "$envfile" ] || sudo -u ubuntu install -m 600 /dev/null "$envfile"
  patch_var() {
    local name=$1 value=$2
    [ -n "$value" ] || return 0
    if ! [[ "$value" =~ ^[A-Za-z0-9._-]+$ ]]; then
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
  patch_var OPENAI_API_KEY "${FOS_OPENAI_API_KEY:-}"
  patch_var GEMINI_API_KEY "${FOS_GEMINI_API_KEY:-}"
  if [ -n "$synced" ]; then echo "env synced:$synced"; fi
}

migrate() {
  sudo -u ubuntu bash -c "cd $API && source .venv/bin/activate && alembic upgrade head"
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
