#!/usr/bin/env bash
# =============================================================================
# uninstall.sh — Remove the platform cleanly (keeps your data).
# =============================================================================
# Delegates to reset-to-normal.sh, the single source of truth for undoing
# everything install.sh ever touched: router DNS back to 192.168.1.1,
# all systemd units/timers, sleep hook, NM dispatcher, dnsmasq drop-in,
# nginx site, resolved.conf default, AppArmor exception, failsafe deadline.
#
# Does NOT delete /opt/parental-safety/collector/data (your database)
# or /opt/parental-safety/.env (your secrets) — pass --delete-opt to the
# reset script for that (irreversible).
#
# Usage:
#   sudo ./infrastructure/scripts/uninstall.sh            # dry-run first
#   sudo ./infrastructure/scripts/uninstall.sh --yes     # DO the uninstall
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--yes" ]]; then
    exec "$SCRIPT_DIR/reset-to-normal.sh" --yes
else
    echo "[uninstall] Showing what would be removed (dry-run). Re-run with --yes to apply."
    echo ""
    exec "$SCRIPT_DIR/reset-to-normal.sh" --dry-run
fi
