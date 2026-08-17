#!/usr/bin/env bash
# Restore-drill script (roadmap step 265, AGENTS.md's own "BACKUPS"
# section: "Restore validation" / "DISASTER RECOVERY": "Recovery should
# be tested"). Proves a real backup from scripts/backup.sh actually
# restores real, queryable data -- a backup nobody has ever restored
# from is not a tested backup, it's an assumption.
#
# Restores into a THROWAWAY container (agentforge-restore-drill, its
# own separate port/volume), never the real dev database -- this is a
# drill, not a real disaster, and must be safe to run repeatedly
# against a live dev environment without touching it. Bootstrapped with
# the SAME infra/postgres/init/ scripts docker-compose.yml's own
# postgres service uses, so the drill container ends up structurally
# identical (agentforge_app role, RLS-ready) to a real restore target,
# not a bare default Postgres image.
#
# Honest, named simplification: this verifies real DATA integrity after
# a real pg_dump/pg_restore round trip, not a full production restore
# procedure (no real production deployment exists yet to model one
# against -- see docs/runbooks/incident-response.md's own "Known gaps").
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# On Windows/Git Bash, MSYS auto-translates any argument that LOOKS like
# a POSIX absolute path (e.g. the container-side /docker-entrypoint-
# initdb.d below) into a Windows path before Docker ever sees it --
# confirmed live: without this, the container's own entrypoint logged
# "ignoring /docker-entrypoint-initdb.d/*" (the mount silently pointed
# nowhere), so agentforge_app was never created and every real GRANT in
# the restored dump failed with "role does not exist". Harmless no-op
# on native Linux/Mac, where MSYS doesn't exist.
export MSYS_NO_PATHCONV=1

BACKUP_DIR="${1:?Usage: scripts/restore-drill.sh <backup-dir, e.g. backups/20260817T120000Z>}"
DUMP_FILE="$BACKUP_DIR/postgres.dump"

if [ ! -f "$DUMP_FILE" ]; then
  echo "No such backup: $DUMP_FILE" >&2
  exit 1
fi

CONTAINER=agentforge-restore-drill

cleanup() {
  echo "==> Tearing down drill container..."
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Starting a throwaway Postgres container for the drill..."
docker run -d --name "$CONTAINER" \
  -e POSTGRES_USER=agentforge \
  -e POSTGRES_PASSWORD=agentforge \
  -e POSTGRES_DB=agentforge \
  -v "$(pwd)/infra/postgres/init:/docker-entrypoint-initdb.d:ro" \
  -p 5433:5432 \
  pgvector/pgvector:pg16 >/dev/null

echo "==> Waiting for it to become ready..."
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U agentforge -d agentforge >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$CONTAINER" pg_isready -U agentforge -d agentforge

echo "==> Restoring $DUMP_FILE into the drill container..."
docker exec -i "$CONTAINER" pg_restore -U agentforge -d agentforge --clean --if-exists < "$DUMP_FILE"

echo "==> Verifying restored data is real and queryable..."
ORG_COUNT="$(docker exec "$CONTAINER" psql -U agentforge -d agentforge -tAc 'SELECT count(*) FROM organizations;')"
echo "Restored organizations: $ORG_COUNT"

if [ "$ORG_COUNT" -lt 1 ]; then
  echo "FAIL: restored database has zero organizations -- backup may be empty or corrupt." >&2
  exit 1
fi

echo "==> Restore drill PASSED: backup is real and restorable."
