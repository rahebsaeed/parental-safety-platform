#!/usr/bin/env bash
# =============================================================================
# uninstall.sh — Remove systemd units, nginx config, and service account
# =============================================================================
# Does NOT delete /opt/parental-safety/collector/data (your database)
# or /opt/parental-safety/.env (your secrets). Run manually to delete those.
#
# Usage:
#   sudo ./infrastructure/scripts/uninstall.sh
# =============================================================================
set -euo pipefail

INSTALL_ROOT="/opt/parental-safety"
SERVICE_USER="parental-monitor"
SERVICES=(parental-monitor-api parental-monitor-collector)
NGINX_CONF="/etc/nginx/sites-enabled/parental-monitor"
NGINX_AVAIL="/etc/nginx/sites-available/parental-monitor"
SYSTEMD_DIR="/etc/systemd/system"

[[ "$EUID" -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }

echo "[uninstall] Stopping and disabling services..."
for svc in "${SERVICES[@]}"; do
    systemctl stop "$svc"    2>/dev/null && echo "  Stopped  $svc" || true
    systemctl disable "$svc" 2>/dev/null && echo "  Disabled $svc" || true
    rm -f "$SYSTEMD_DIR/${svc}.service"
done
systemctl daemon-reload

echo "[uninstall] Removing nginx configuration..."
rm -f "$NGINX_CONF" "$NGINX_AVAIL"
if command -v nginx &>/dev/null && nginx -t 2>/dev/null; then
    systemctl reload nginx
fi

echo "[uninstall] Uninstall complete."
echo ""
echo "  Data and .env preserved at:"
echo "    $INSTALL_ROOT/collector/data/"
echo "    $INSTALL_ROOT/.env"
echo ""
echo "  To fully remove everything:"
echo "    sudo rm -rf $INSTALL_ROOT"
echo "    sudo userdel $SERVICE_USER"
