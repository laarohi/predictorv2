#!/usr/bin/env bash
#
# Daily Postgres backup → Cloudflare R2.
# Runs on the VPS host (not in a container). Designed for cron:
#   0 3 * * * /home/luke/predictorv2/ops/backup-db.sh >> /home/luke/predictor-backup.log 2>&1
#
# Reads R2_* and DATABASE_PASSWORD from ../.env (the prod .env beside docker-compose.yml).
# Requires: docker, rclone, gzip (all on the VPS host).
#
# Exits non-zero on any failure — cron's MAILTO or your log scrape catches it loud.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$REPO_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE" >&2
  exit 1
fi

# Load all KEY=VALUE pairs from .env into the environment.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Required values — fail fast if any missing.
: "${R2_ACCESS_KEY_ID:?missing in .env}"
: "${R2_SECRET_ACCESS_KEY:?missing in .env}"
: "${R2_ENDPOINT:?missing in .env}"
: "${R2_BUCKET:?missing in .env}"

# rclone config via env vars — no rclone.conf needed.
# Remote name is "r2"; reference as r2:<bucket>/...
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_R2_ENDPOINT="$R2_ENDPOINT"
export RCLONE_CONFIG_R2_REGION=auto
export RCLONE_CONFIG_R2_ACL=private
# Skip the pre-flight HeadBucket/CreateBucket attempt rclone does by default.
# That call requires bucket-management (Admin) permission; without this flag,
# Object-Read-Write tokens get 403 even though they have valid PutObject perms.
# See https://forum.rclone.org/t/cannot-copy-to-cloudflare-r2-using-copy-failed-to-copy-forbidden-status-code-403-request-id-host-id/41928
export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true

TIMESTAMP=$(date -u +%Y%m%d-%H%M%SZ)
DUMP_FILE="/tmp/predictor-${TIMESTAMP}.sql.gz"
RETENTION_DAYS=14

log() { echo "[$(date -u +%FT%TZ)] $*"; }

log "Starting backup for timestamp $TIMESTAMP"

# Dump from inside the db container, gzip on the host.
# --clean --if-exists makes the dump self-contained for restore.
# --no-owner --no-acl makes it portable across different db role setups.
cd "$REPO_DIR"
docker compose exec -T db \
  pg_dump -U predictor --no-owner --no-acl --clean --if-exists predictor \
  | gzip -9 > "$DUMP_FILE"

DUMP_SIZE=$(stat -c%s "$DUMP_FILE")
DUMP_SIZE_H=$(numfmt --to=iec "$DUMP_SIZE")
log "Dump created: $DUMP_FILE ($DUMP_SIZE_H)"

# Upload. rclone copy is idempotent — re-uploading same path is a no-op.
rclone copy --quiet "$DUMP_FILE" "r2:${R2_BUCKET}/"
log "Uploaded to r2:${R2_BUCKET}/predictor-${TIMESTAMP}.sql.gz"

# Local cleanup.
rm -f "$DUMP_FILE"

# Prune old backups in R2. --min-age uses object age, not filename date.
PRUNED=$(rclone delete --min-age "${RETENTION_DAYS}d" --verbose "r2:${R2_BUCKET}/" 2>&1 | grep -c "Deleted" || true)
log "Pruned $PRUNED objects older than ${RETENTION_DAYS}d"

log "Backup complete."
