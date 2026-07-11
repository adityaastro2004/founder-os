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
