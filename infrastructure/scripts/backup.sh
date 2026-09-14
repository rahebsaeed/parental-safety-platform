#!/usr/bin/env bash
# =============================================================================
# backup.sh — Online hot backup of the Parental Safety Platform database
# =============================================================================
# Uses SQLite's built-in .backup command, which is safe while the database
# is live (WAL mode handles concurrent access). Does not require stopping
# any services.
#
# Usage:
#   ./backup.sh                         # backup to default location
#   ./backup.sh /mnt/usb/backups        # backup to a specific directory
#
# Cron example (daily at 03:00):
#   0 3 * * * /opt/parental-safety/infrastructure/scripts/backup.sh \
#             /opt/parental-safety/backups >> /var/log/parental-safety/backup.log 2>&1
# =============================================================================
set -euo pipefail

# --- Configuration -----------------------------------------------------------
INSTALL_ROOT="${INSTALL_ROOT:-/opt/parental-safety}"
DB_PATH="${DB_PATH:-$INSTALL_ROOT/collector/data/discovery.sqlite3}"
BACKUP_DIR="${1:-$INSTALL_ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# --- Validation --------------------------------------------------------------
if [[ ! -f "$DB_PATH" ]]; then
    echo "[ERROR] Database not found at: $DB_PATH" >&2
    exit 1
fi

if ! command -v sqlite3 &>/dev/null; then
    echo "[ERROR] sqlite3 CLI not installed. Install with: sudo apt install sqlite3" >&2
    exit 1
fi

# --- Run backup --------------------------------------------------------------
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/discovery_${TIMESTAMP}.sqlite3.bak"

echo "[$(date -Iseconds)] Starting backup: $DB_PATH → $BACKUP_FILE"
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Verify the backup is a valid SQLite database
INTEGRITY=$(sqlite3 "$BACKUP_FILE" "PRAGMA integrity_check;" 2>&1)
if [[ "$INTEGRITY" != "ok" ]]; then
    echo "[ERROR] Backup integrity check failed: $INTEGRITY" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "[$(date -Iseconds)] Backup complete: $BACKUP_FILE ($SIZE) — integrity: ok"

# --- Rotate old backups -------------------------------------------------------
if [[ "$RETENTION_DAYS" -gt 0 ]]; then
    DELETED=$(find "$BACKUP_DIR" -name "discovery_*.sqlite3.bak" \
        -mtime +"$RETENTION_DAYS" -print -delete | wc -l)
    if [[ "$DELETED" -gt 0 ]]; then
        echo "[$(date -Iseconds)] Rotated $DELETED backup(s) older than ${RETENTION_DAYS} days"
    fi
fi
