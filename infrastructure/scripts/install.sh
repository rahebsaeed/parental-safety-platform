#!/usr/bin/env bash
# =============================================================================
# install.sh — Idempotent installer for the Parental Safety Platform
# =============================================================================
# Installs the platform to /opt/parental-safety, creates the parental-monitor
# system user, builds the frontend, runs database migrations, configures nginx,
# and enables all systemd services.
#
# Run as root (or with sudo):
#   sudo ./infrastructure/scripts/install.sh
#
# Re-running is safe — all steps check before acting.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INSTALL_ROOT="/opt/parental-safety"
SERVICE_USER="parental-monitor"
SERVICE_GROUP="parental-monitor"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
NGINX_CONF_NAME="parental-monitor"

SYSTEMD_DIR="/etc/systemd/system"
SERVICES=(parental-monitor-collector parental-monitor-api dnsmasq)

# ---------------------------------------------------------------------------
log() { echo -e "\e[1;34m[install]\e[0m $*"; }
ok()  { echo -e "\e[1;32m[  OK  ]\e[0m $*"; }
warn(){ echo -e "\e[1;33m[ WARN ]\e[0m $*"; }
err() { echo -e "\e[1;31m[ERROR ]\e[0m $*" >&2; exit 1; }
# ---------------------------------------------------------------------------

[[ "$EUID" -eq 0 ]] || err "Run this script as root: sudo $0"

# 1. Create system user ---------------------------------------------------
log "Creating system user '$SERVICE_USER'..."
if id "$SERVICE_USER" &>/dev/null; then
    ok "User '$SERVICE_USER' already exists"
else
    useradd --system \
            --no-create-home \
            --home-dir "$INSTALL_ROOT" \
            --shell /usr/sbin/nologin \
            --comment "Parental Safety Platform daemon account" \
            "$SERVICE_USER"
    ok "Created system user '$SERVICE_USER'"
fi

# 2. Create install directory ----------------------------------------------
log "Setting up $INSTALL_ROOT..."
mkdir -p "$INSTALL_ROOT"/{collector/data,backups,frontend}
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_ROOT"

# 3. Copy project files ----------------------------------------------------
log "Syncing project files to $INSTALL_ROOT..."
rsync -a --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='node_modules' \
    --exclude='frontend/dist' \
    --exclude='collector/data' \
    --exclude='backups' \
    --exclude='.cache' \
    --exclude='.rustup' \
    --exclude='.env' \
    "$PROJECT_SRC/" "$INSTALL_ROOT/"
# Remove stale per-user caches left by earlier buggy runs (npm/cargo ran as
# the service user with HOME=$INSTALL_ROOT and polluted the install root).
rm -rf "$INSTALL_ROOT/.cache" "$INSTALL_ROOT/.rustup"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_ROOT"
ok "Project files synced"

# 3b. Environment file (BEFORE migrations so Alembic sees production paths) --
log "Setting up .env..."
if [[ ! -f "$INSTALL_ROOT/.env" ]]; then
    cp "$INSTALL_ROOT/.env.example" "$INSTALL_ROOT/.env"
    # Generate a random password if the default is still set
    DEFAULT_PASS="admin123"
    RANDOM_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
    sed -i "s|PARENT_PASSWORD=$DEFAULT_PASS|PARENT_PASSWORD=$RANDOM_PASS|g" \
        "$INSTALL_ROOT/.env" 2>/dev/null || true
    # Pin production to absolute DB/log paths. The shipped .env.example uses
    # dev-relative defaults (./data/...) which resolve to the wrong directory
    # when services run with WorkingDirectory=/opt/parental-safety.
    # backend/app/core/config.py also falls back to /opt, but explicit is better.
    if ! grep -q "^DATABASE_PATH=" "$INSTALL_ROOT/.env"; then
        echo "DATABASE_PATH=/opt/parental-safety/collector/data/discovery.sqlite3" >> "$INSTALL_ROOT/.env"
    elif grep -q "^DATABASE_PATH=$" "$INSTALL_ROOT/.env"; then
        sed -i "s|^DATABASE_PATH=$|DATABASE_PATH=/opt/parental-safety/collector/data/discovery.sqlite3|" "$INSTALL_ROOT/.env"
    fi
    if ! grep -q "^DISCOVERY_DB_PATH=" "$INSTALL_ROOT/.env"; then
        echo "DISCOVERY_DB_PATH=/opt/parental-safety/collector/data/discovery.sqlite3" >> "$INSTALL_ROOT/.env"
    elif grep -q "^DISCOVERY_DB_PATH=$" "$INSTALL_ROOT/.env" || grep -q "^DISCOVERY_DB_PATH=\./data" "$INSTALL_ROOT/.env"; then
        sed -i "s|^DISCOVERY_DB_PATH=.*|DISCOVERY_DB_PATH=/opt/parental-safety/collector/data/discovery.sqlite3|" "$INSTALL_ROOT/.env"
    fi
    if ! grep -q "^DNS_LOG_PATH=" "$INSTALL_ROOT/.env"; then
        echo "DNS_LOG_PATH=/var/log/parental-safety/dnsmasq.log" >> "$INSTALL_ROOT/.env"
    fi
    chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_ROOT/.env"
    chmod 640 "$INSTALL_ROOT/.env"
    warn ".env created with a random PARENT_PASSWORD — check $INSTALL_ROOT/.env"
else
    ok ".env already exists — skipping (not overwriting)"
fi

# 4. Python virtual environment -------------------------------------------
log "Setting up Python virtual environment..."
if [[ ! -f "$INSTALL_ROOT/collector/.venv/bin/python" ]]; then
    sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_ROOT/collector/.venv"
fi
sudo -u "$SERVICE_USER" "$INSTALL_ROOT/collector/.venv/bin/pip" install \
    --quiet --upgrade pip
# Install the collector package (dns daemon)
sudo -u "$SERVICE_USER" "$INSTALL_ROOT/collector/.venv/bin/pip" install \
    --quiet -e "$INSTALL_ROOT/collector"
# Install the backend package from backend/ (pyproject.toml has where=[".."]
# so editable install must be run from backend/ subdirectory)
sudo -u "$SERVICE_USER" "$INSTALL_ROOT/collector/.venv/bin/pip" install \
    --quiet -e "$INSTALL_ROOT/backend"
ok "Python environment ready"

# 5. Alembic migrations ---------------------------------------------------
# NOTE: backend/alembic.ini uses script_location=%(here)s/alembic so this
# works from $INSTALL_ROOT (where .env lives for DATABASE_PATH lookup).
log "Running database migrations..."
cd "$INSTALL_ROOT"
sudo -u "$SERVICE_USER" "$INSTALL_ROOT/collector/.venv/bin/python" \
    -m alembic -c "$INSTALL_ROOT/backend/alembic.ini" upgrade head
ok "Migrations complete"

# 6. Frontend production build --------------------------------------------
log "Building React frontend..."
# node is often installed user-local (e.g. ~/.local/bin via hermes/fnm) which
# is NOT on root's PATH under sudo. Also check the invoking user's local bin.
if ! command -v node &>/dev/null && [[ -n "${SUDO_USER:-}" ]]; then
    SUDO_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
    if [[ -x "$SUDO_HOME/.local/bin/node" ]]; then
        export PATH="$SUDO_HOME/.local/bin:$PATH"
        log "Added $SUDO_HOME/.local/bin to PATH (found node for $SUDO_USER)"
    fi
fi
if command -v node &>/dev/null; then
    cd "$INSTALL_ROOT/frontend"
    # npm runs as the calling user (root during install) because npm needs
    # cache access and network. The built dist/ is then chowned to the
    # service user below.
    npm ci --prefer-offline --silent
    npm run build
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_ROOT/frontend/dist"
    ok "Frontend built: $INSTALL_ROOT/frontend/dist"
else
    warn "node not found — skipping frontend build."
    warn "Install Node.js system-wide (curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs) then re-run this script."
fi

# 7. Set data directory permissions ----------------------------------------
log "Securing data directory..."
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_ROOT/collector/data"
chmod 770 "$INSTALL_ROOT/collector/data"
if [[ -f "$INSTALL_ROOT/collector/data/discovery.sqlite3" ]]; then
    chmod 660 "$INSTALL_ROOT/collector/data/discovery.sqlite3"
fi

# 8. Log directory ----------------------------------------------------------
log "Creating log directory..."
mkdir -p /var/log/parental-safety
chown "$SERVICE_USER:$SERVICE_GROUP" /var/log/parental-safety
chmod 750 /var/log/parental-safety
ok "Log directory: /var/log/parental-safety"

# 9. Environment file — already created in step 3b (before migrations) ------
log "Verifying .env..."
if [[ -f "$INSTALL_ROOT/.env" ]]; then
    ok ".env present: $INSTALL_ROOT/.env"
else
    warn ".env missing (unexpected) — see step 3b"
fi

# 10. Nginx configuration --------------------------------------------------
log "Configuring nginx..."
if command -v nginx &>/dev/null; then
    # Ensure the WebSocket upgrade map is in nginx.conf http block
    NGINX_CONF="/etc/nginx/nginx.conf"
    if ! grep -q "connection_upgrade" "$NGINX_CONF" 2>/dev/null; then
        # Insert the map block before the first 'server {' or 'include' in http block
        sed -i '/http {/a\\n\tmap $http_upgrade $connection_upgrade {\n\t\tdefault upgrade;\n\t\t'"''"' close;\n\t}' "$NGINX_CONF"
        ok "WebSocket upgrade map added to nginx.conf"
    fi

    cp "$INSTALL_ROOT/infrastructure/nginx/parental-monitor.conf" \
       "$NGINX_SITES_AVAILABLE/$NGINX_CONF_NAME"

    if [[ ! -L "$NGINX_SITES_ENABLED/$NGINX_CONF_NAME" ]]; then
        ln -sf "$NGINX_SITES_AVAILABLE/$NGINX_CONF_NAME" \
               "$NGINX_SITES_ENABLED/$NGINX_CONF_NAME"
    fi

    # Remove default site if it conflicts on port 80
    if [[ -L "$NGINX_SITES_ENABLED/default" ]]; then
        warn "Removing nginx default site (conflicts on port 80)"
        rm -f "$NGINX_SITES_ENABLED/default"
    fi

    nginx -t && systemctl reload nginx
    ok "nginx configured and reloaded"
else
    warn "nginx not found — skipping. Install with: sudo apt install nginx"
fi

# 10. Disable systemd-resolved stub listener (avoids 127.0.0.53
#     intercepting LAN DNS before it reaches dnsmasq) -------------
if [[ -f /etc/systemd/resolved.conf ]]; then
    if ! grep -q "DNSStubListener=no" /etc/systemd/resolved.conf 2>/dev/null; then
        sed -i 's/^#DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf
        # Also ensure it's set explicitly
        grep -q "^DNSStubListener=" /etc/systemd/resolved.conf || \
            echo "DNSStubListener=no" >> /etc/systemd/resolved.conf
        systemctl restart systemd-resolved 2>/dev/null || true
        ok "Disabled systemd-resolved stub listener"
    fi
fi

# 11. Systemd units --------------------------------------------------------
log "Installing systemd service units..."
for unit_file in "$INSTALL_ROOT/infrastructure/systemd/"*.service; do
    unit_name=$(basename "$unit_file")
    cp "$unit_file" "$SYSTEMD_DIR/$unit_name"
    ok "Installed $unit_name"
done
for unit_file in "$INSTALL_ROOT/infrastructure/systemd/"*.timer; do
    [ -e "$unit_file" ] || continue
    unit_name=$(basename "$unit_file")
    cp "$unit_file" "$SYSTEMD_DIR/$unit_name"
    ok "Installed $unit_name"
done

systemctl daemon-reload

for timer in parental-monitor-scan.timer parental-monitor-ai-sync.timer; do
    if [ -f "$SYSTEMD_DIR/$timer" ]; then
        systemctl enable "$timer"
        ok "Enabled $timer"
    fi
done

for svc in "${SERVICES[@]}"; do
    systemctl enable "$svc"
    systemctl restart "$svc"
    ok "Enabled and started $svc"
done

# 12. Make scripts executable ----------------------------------------------
chmod +x "$INSTALL_ROOT/infrastructure/scripts/"*.sh

# 13. Final status ---------------------------------------------------------
echo ""
log "======================================================"
log " Installation complete!"
log "======================================================"
for svc in "${SERVICES[@]}"; do
    STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    echo "  $svc: $STATUS"
done
echo ""
echo "  Dashboard:  http://192.168.1.20/"
echo "  API docs:   http://192.168.1.20/api/docs"
echo ""
echo "  Password:   cat $INSTALL_ROOT/.env | grep PARENT_PASSWORD"
echo "  Logs:       journalctl -fu parental-monitor-collector"
echo "              journalctl -fu parental-monitor-api"
echo ""

# 11. Router DNS automation --------------------------------------------
# Guard service: dnsmasq DNS while the PC is up, router fallback on the way
# down. A persistent guard (ExecStop) is stopped BEFORE NetworkManager at
# shutdown, so the fallback still has a live network — the old
# Before=shutdown.target starter raced WiFi teardown and usually lost.
# Suspend/hibernate is covered by the system-sleep hook (network is still
# up when pre-sleep hooks run). Logout needs nothing: the WiFi connection
# is system-wide, so it survives logout.

echo ""
echo "  [Router DNS Automation]"

if [ ! -f "/scripts/router-dns.sh" ]; then
    if [ -f "/infrastructure/scripts/router-dns.sh" ]; then
        cp "/infrastructure/scripts/router-dns.sh"            "/scripts/router-dns.sh" 2>/dev/null || true
        chmod +x "/scripts/router-dns.sh" 2>/dev/null || true
    fi
fi

cp "$PROJECT_ROOT/infrastructure/systemd/router-dns-guard.service" \
    /etc/systemd/system/router-dns-guard.service 2>/dev/null || true
cp "$PROJECT_ROOT/infrastructure/scripts/router-dns-sleep" \
    /etc/systemd/system-sleep/router-dns 2>/dev/null || true
chmod +x /etc/systemd/system-sleep/router-dns 2>/dev/null || true

# Retire the racy on/off pair in favour of the guard.
systemctl disable router-dns-on.service 2>/dev/null || true
systemctl disable router-dns-off.service 2>/dev/null || true
rm -f /etc/systemd/system/router-dns-on.service \
    /etc/systemd/system/router-dns-off.service 2>/dev/null || true

systemctl daemon-reload 2>/dev/null || true
systemctl enable router-dns-guard.service 2>/dev/null || true
echo "  Router DNS automation installed (guard + suspend hook)"

# 12. NetworkManager dispatcher (WiFi lid close → set router DNS) ----
log "Installing NetworkManager WiFi dispatcher..."
NM_DISPATCHER_SRC="$PROJECT_ROOT/infrastructure/scripts/99-router-dns-switch"
NM_DISPATCHER_DST="/etc/NetworkManager/dispatcher.d/99-router-dns-switch"
if [ -f "$NM_DISPATCHER_SRC" ]; then
    cp "$NM_DISPATCHER_SRC" "$NM_DISPATCHER_DST" 2>/dev/null || true
    chmod +x "$NM_DISPATCHER_DST" 2>/dev/null || true
    ok "NetworkManager dispatcher installed"
else
    warn "99-router-dns-switch not found, skipping"
fi

# 13. Systemd units ------------------------------------------------------
log "Installing systemd service units..."

# 14. Router DHCP client list script -------------------------------
log "Installing router DHCP client list script..."
if [ -f "/infrastructure/scripts/router-dhcp-clients.sh" ]; then
    cp "/infrastructure/scripts/router-dhcp-clients.sh"        "/scripts/router-dhcp-clients.sh" 2>/dev/null || true
    chmod +x "/scripts/router-dhcp-clients.sh" 2>/dev/null || true
    ok "Router DHCP client list script installed"
fi
