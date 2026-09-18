#!/usr/bin/env bash
# =============================================================================
# reset-to-normal.sh — Emergency "return everything to normal" reset.
#
# If anything goes wrong (e.g. PC connects to WiFi but has no internet),
# this script undoes EVERYTHING the platform changed on this PC and on the
# router, while KEEPING your data:
#
#   1. Router DNS back to default (192.168.1.1) so the LAN resolves again
#   2. Stop + disable + remove all platform systemd units and timers
#      (collector, api, scan, ai-sync, dns-revert, dnsmasq-if-ours,
#       retired router-dns-guard/on/off)
#   3. Remove the sleep hook (/etc/systemd/system-sleep/router-dns) and the
#      NetworkManager dispatcher (99-router-dns-switch)
#   4. Remove our dnsmasq drop-in (/etc/dnsmasq.d/parental-safety-phase2.conf)
#   5. Remove our nginx site config (reload nginx afterwards)
#   6. Restore /etc/systemd/resolved.conf stub-listener default
#   7. Remove our AppArmor exception lines for /var/log/parental-safety
#   8. Clear the 3h failsafe deadline file
#
# KEPT by default (your data + the OS stay intact):
#   /opt/parental-safety (database, .env, code — services just stay stopped),
#   /var/log/parental-safety, the parental-monitor user, nginx/dnsmasq
#   packages, Tailscale, and the generic nginx connection_upgrade map.
#
# Usage:
#   sudo ./infrastructure/scripts/reset-to-normal.sh --dry-run   # show plan only
#   sudo ./infrastructure/scripts/reset-to-normal.sh --yes       # DO the reset
#   sudo ./infrastructure/scripts/reset-to-normal.sh --yes --delete-opt   # also rm -rf /opt/parental-safety
#   sudo ./infrastructure/scripts/reset-to-normal.sh --yes --delete-user  # also delete parental-monitor user
#        (implies nothing else; combine flags as needed)
#
# To bring the platform back afterwards: bash infrastructure/scripts/install.sh
# =============================================================================
set -u

INSTALL_ROOT="/opt/parental-safety"
SERVICE_USER="parental-monitor"
SYSTEMD_DIR="/etc/systemd/system"
FAILURES=0
DRY_RUN=1
DELETE_OPT=0
DELETE_USER=0

for arg in "$@"; do
    case "$arg" in
        --yes) DRY_RUN=0 ;;
        --dry-run) DRY_RUN=1 ;;
        --delete-opt) DELETE_OPT=1 ;;
        --delete-user) DELETE_USER=1 ;;
        -h|--help)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *) echo "Unknown flag: $arg (see --help)" >&2; exit 2 ;;
    esac
done

log()  { echo -e "\e[1;34m[reset]\e[0m $*"; }
ok()   { echo -e "\e[1;32m[  OK ]\e[0m $*"; }
warn() { echo -e "\e[1;33m[ WARN]\e[0m $*"; }
fail() { echo -e "\e[1;31m[ FAIL]\e[0m $*" >&2; FAILURES=$((FAILURES+1)); }

[[ "$EUID" -eq 0 ]] || { echo "Run as root: sudo $0 --dry-run | --yes" >&2; exit 1; }

if [[ "$DRY_RUN" -eq 1 ]]; then
    log "DRY-RUN — nothing will be changed. Re-run with --yes to act."
fi
run() {
    # run <description> <command...>: prints, then executes unless dry-run.
    local desc="$1"; shift
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [would] $desc: $*"
        return 0
    fi
    echo "  [do] $desc"
    if "$@" 2>/dev/null; then
        ok "$desc"
    else
        warn "$desc did not apply (already absent or service missing?)"
    fi
}

# -- Step 0: heal the router FIRST -------------------------------------------
# If the LAN points at this PC for DNS, every later stop would black-hole
# name resolution. Restoring 192.168.1.1 first keeps internet alive.
log "Step 0 — router DNS back to default (192.168.1.1)..."
ROUTER_SCRIPT=""
for candidate in "$INSTALL_ROOT/scripts/router-dns.sh" \
                 "$INSTALL_ROOT/infrastructure/scripts/router-dns.sh" \
                 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/router-dns.sh"; do
    if [[ -x "$candidate" ]]; then ROUTER_SCRIPT="$candidate"; break; fi
done
if [[ -z "$ROUTER_SCRIPT" ]]; then
    fail "no router-dns.sh found — fix the router by hand: http://192.168.1.1 → Settings → Network → DNS/DNS2 = 192.168.1.1"
else
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [would] $ROUTER_SCRIPT off"
    elif "$ROUTER_SCRIPT" off 2>&1 | tail -n 3; then
        ok "router DNS reverted (or already default)"
    else
        fail "$ROUTER_SCRIPT off failed — set DNS/DNS2=192.168.1.1 by hand at http://192.168.1.1"
    fi
fi

# -- Step 1: stop/disable/remove systemd units -------------------------------
log "Step 1 — platform systemd units and timers..."
UNITS=(parental-monitor-collector.service parental-monitor-api.service
       parental-monitor-scan.service parental-monitor-scan.timer
       parental-monitor-ai-sync.service parental-monitor-ai-sync.timer
       parental-monitor-dns-revert.service parental-monitor-dns-revert.timer
       router-dns-guard.service router-dns-on.service router-dns-off.service)
for unit in "${UNITS[@]}"; do
    base="${unit%.service}"; base="${base%.timer}"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [would] systemctl disable --now $unit; rm -f $SYSTEMD_DIR/$unit"
        continue
    fi
    systemctl stop "$unit" 2>/dev/null || true
    systemctl disable "$unit" 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/$unit"
    # also drop a possible override drop-in
    rm -rf "$SYSTEMD_DIR/${unit}.d"
    echo "  removed $unit (if it existed)"
done

# dnsmasq.service is a GENERIC name — remove ONLY if it is ours.
if [[ -f "$SYSTEMD_DIR/dnsmasq.service" ]]; then
    if grep -q "parental-safety-phase2" "$SYSTEMD_DIR/dnsmasq.service" 2>/dev/null; then
        run "remove our dnsmasq.service unit" systemctl disable --now dnsmasq.service
        if [[ "$DRY_RUN" -eq 0 ]]; then rm -f "$SYSTEMD_DIR/dnsmasq.service"; ok "removed our dnsmasq.service"; fi
    else
        warn "dnsmasq.service exists but is NOT ours — leaving it alone"
    fi
else
    echo "  dnsmasq.service not present — nothing to do"
fi
if [[ "$DRY_RUN" -eq 0 ]]; then systemctl daemon-reload 2>/dev/null || true; fi

# -- Step 2: sleep hook + NM dispatcher ---------------------------------------
log "Step 2 — sleep hook and NetworkManager dispatcher..."
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [would] rm -f /etc/systemd/system-sleep/router-dns /etc/NetworkManager/dispatcher.d/99-router-dns-switch"
else
    rm -f /etc/systemd/system-sleep/router-dns && echo "  removed system-sleep hook (if it existed)"
    rm -f /etc/NetworkManager/dispatcher.d/99-router-dns-switch && echo "  removed NM dispatcher (if it existed)"
fi

# -- Step 3: dnsmasq drop-in ---------------------------------------------------
log "Step 3 — our dnsmasq config..."
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [would] rm -f /etc/dnsmasq.d/parental-safety-phase2.conf"
else
    rm -f /etc/dnsmasq.d/parental-safety-phase2.conf && echo "  removed parental-safety-phase2.conf (if it existed)"
fi

# -- Step 4: nginx site ---------------------------------------------------------
log "Step 4 — nginx site config..."
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [would] rm -f /etc/nginx/sites-enabled/parental-monitor /etc/nginx/sites-available/parental-monitor; nginx -t && systemctl reload nginx"
else
    rm -f /etc/nginx/sites-enabled/parental-monitor /etc/nginx/sites-available/parental-monitor
    echo "  removed nginx parental-monitor site (if it existed)"
    if command -v nginx &>/dev/null && nginx -t 2>/dev/null; then
        systemctl reload nginx 2>/dev/null && ok "nginx reloaded" || warn "nginx reload failed — run: sudo nginx -t"
    fi
    # NOTE: the generic 'connection_upgrade' map in nginx.conf is left alone:
    # it is harmless and other sites may use it.
fi

# -- Step 5: systemd-resolved stub listener --------------------------------------
log "Step 5 — restore systemd-resolved stub listener default..."
RESOLVED_CONF="/etc/systemd/resolved.conf"
if [[ -f "$RESOLVED_CONF" ]] && grep -q "^DNSStubListener=no" "$RESOLVED_CONF" 2>/dev/null; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [would] comment out DNSStubListener=no in $RESOLVED_CONF; systemctl restart systemd-resolved"
    else
        sed -i 's/^DNSStubListener=no/#DNSStubListener=yes/' "$RESOLVED_CONF"
        systemctl restart systemd-resolved 2>/dev/null || true
        ok "resolved.conf restored to default"
    fi
else
    echo "  resolved.conf already default — nothing to do"
fi

# -- Step 6: AppArmor exception ----------------------------------------------------
log "Step 6 — AppArmor dnsmasq exception..."
AA_LOCAL="/etc/apparmor.d/local/usr.sbin.dnsmasq"
if [[ -f "$AA_LOCAL" ]] && grep -q "/var/log/parental-safety" "$AA_LOCAL" 2>/dev/null; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [would] delete /var/log/parental-safety lines from $AA_LOCAL and reload the profile"
    else
        sed -i '\|/var/log/parental-safety|d' "$AA_LOCAL"
        if command -v apparmor_parser &>/dev/null && [[ -f /etc/apparmor.d/usr.sbin.dnsmasq ]]; then
            apparmor_parser -r /etc/apparmor.d/usr.sbin.dnsmasq 2>/dev/null || true
        fi
        ok "AppArmor exception removed"
    fi
else
    echo "  no AppArmor exception present — nothing to do"
fi

# -- Step 7: failsafe deadline state ------------------------------------------------
log "Step 7 — clear failsafe deadline state..."
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [would] rm -f /var/lib/parental-safety/router-dns-deadline"
else
    rm -f /var/lib/parental-safety/router-dns-deadline && echo "  deadline cleared (if it existed)"
fi

# -- Optional nuclear flags ----------------------------------------------------------
if [[ "$DELETE_OPT" -eq 1 ]]; then
    run "delete $INSTALL_ROOT (code, DB, .env — IRREVERSIBLE)" rm -rf "$INSTALL_ROOT"
fi
if [[ "$DELETE_USER" -eq 1 ]]; then
    if id "$SERVICE_USER" &>/dev/null; then
        run "delete user $SERVICE_USER" userdel "$SERVICE_USER"
    else
        echo "  user $SERVICE_USER absent — nothing to do"
    fi
fi

# -- Summary ---------------------------------------------------------------------------
echo ""
log "======================================================"
if [[ "$DRY_RUN" -eq 1 ]]; then
    log " Dry-run complete — re-run with --yes to apply."
else
    log " Reset complete."
fi
log "======================================================"
echo "  Preserved (your data): $INSTALL_ROOT/collector/data/ (DB)"
echo "                          $INSTALL_ROOT/.env (password)"
echo "                          /var/log/parental-safety/ (logs)"
echo "  To verify:"
echo "    systemctl list-unit-files | grep -E 'parental|router-dns'  # expect empty"
echo "    ls /etc/systemd/system-sleep/router-dns /etc/NetworkManager/dispatcher.d/99-router-dns-switch  # expect missing"
echo "    curl http://192.168.1.1  # router reachable; LAN DNS = 192.168.1.1"
echo "  To bring the platform back:"
echo "    bash infrastructure/scripts/install.sh"
echo ""
if [[ "$FAILURES" -gt 0 ]]; then
    warn "$FAILURES step(s) need manual attention (see FAIL lines above)"
    exit 1
fi
exit 0
