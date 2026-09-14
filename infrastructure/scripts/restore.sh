#!/usr/bin/env bash
# =============================================================================
# restore.sh — Restore the Parental Safety Platform database from a backup
# =============================================================================
# Stops the API and collector services, replaces the live database with the
# chosen backup file, then restarts services.
#
# Usage:
#   sudo ./restore.sh /opt/parental-safety/backups/discovery_20260913_030000.sqlite3.bak
# =============================================================================
set -euo pipefail

# --- Configuration -----------------------------------------------------------
INSTALL_ROOT="${INSTALL_ROOT:-/opt/parental-safety}"
DB_PATH="${DB_PATH:-$INSTALL_ROOT/collector/data/discovery.sqlite3}"
SERVICES=(parental-monitor-api parental-monitor-collector)

# --- Argument check ----------------------------------------------------------
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <backup-file.sqlite3.bak>" >&2
    exit 1
fi
BACKUP_FILE="$1"

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "[ERROR] Backup file not found: $BACKUP_FILE" >&2
    exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
    echo "[ERROR] This script must be run as root (sudo $0 $*)" >&2
    exit 1
fi

# --- Validate backup ---------------------------------------------------------
if ! command -v sqlite3 &>/dev/null; then
    echo "[ERROR] sqlite3 not installed. Run: sudo apt install sqlite3" >&2
    exit 1
fi

INTEGRITY=$(sqlite3 "$BACKUP_FILE" "PRAGMA integrity_check;" 2>&1)
if [[ "$INTEGRITY" != "ok" ]]; then
    echo "[ERROR] Backup file failed integrity check: $INTEGRITY" >&2
    exit 1
fi
echo "[INFO] Backup integrity: ok"

# --- Stop services -----------------------------------------------------------
echo "[INFO] Stopping services..."
for svc in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        systemctl stop "$svc"
        echo "[INFO] Stopped $svc"
    fi
done

# --- Swap database -----------------------------------------------------------
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
if [[ -f "$DB_PATH" ]]; then
    SAFETY_BAK="${DB_PATH%.sqlite3}_pre_restore_${TIMESTAMP}.sqlite3.bak"
    echo "[INFO] Preserving current DB as safety backup: $SAFETY_BAK"
    cp "$DB_PATH" "$SAFETY_BAK"
    # Remove WAL/SHM files to avoid corruption on startup
    rm -f "${DB_PATH}-wal" "${DB_PATH}-shm"
fi

echo "[INFO] Restoring: $BACKUP_FILE → $DB_PATH"
cp "$BACKUP_FILE" "$DB_PATH"
chown parental-monitor:parental-monitor "$DB_PATH"
chmod 660 "$DB_PATH"

# --- Restart services --------------------------------------------------------
echo "[INFO] Restarting services..."
for svc in "${SERVICES[@]}"; do
    systemctl start "$svc"
    echo "[INFO] Started $svc"
done

echo ""
echo "[OK] Restore complete. Current DB: $DB_PATH"
echo "     Safety backup of old DB: ${SAFETY_BAK:-none}"
