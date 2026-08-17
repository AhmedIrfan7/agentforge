#!/usr/bin/env bash
# Backup automation (roadmap step 265, AGENTS.md's own "BACKUPS"/
# "BACKUP STRATEGY" sections: automated, versioned backups).
#
# Scoped to the real, current stack (Docker Compose: Postgres+pgvector,
# MinIO) -- this project has no real production deployment yet
# (Milestone 11), so this backs up the SAME local/self-hosted stack a
# real deployment would eventually replace with managed equivalents
# (RDS snapshots, S3 versioning, etc.), not something aspirational.
#
# Postgres uses a real logical backup (pg_dump -Fc, custom/compressed
# format -- the one format pg_restore can selectively restore from and
# that survives a schema-version mismatch better than a raw file copy).
# A raw copy of .docker-data/postgres while the container is live risks
# an inconsistent snapshot (pages mid-write) -- pg_dump takes a
# consistent snapshot via a real transaction, which a raw file copy
# cannot.
#
# MinIO's own data directory (.docker-data/minio, already a host bind
# mount per docker-compose.yml) is tar'd directly instead -- object
# storage here is just files on disk, written atomically on upload, not
# live-transacted the way Postgres pages are, so a raw copy is a valid,
# real backup for this stack's actual usage pattern.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="backups/${TIMESTAMP}"
mkdir -p "$BACKUP_DIR"

echo "==> Backing up Postgres (agentforge database)..."
docker exec agentforge-postgres pg_dump -U agentforge -Fc agentforge > "$BACKUP_DIR/postgres.dump"

echo "==> Backing up MinIO object storage..."
tar -czf "$BACKUP_DIR/minio-data.tar.gz" -C .docker-data/minio .

echo "==> Backup complete: $BACKUP_DIR"
ls -lh "$BACKUP_DIR"
