#!/usr/bin/env bash
# infrastructure/dnsmasq/setup.sh
#
# Phase 2 DNS Observation — dnsmasq setup and validation script.
#
# Usage:
#   sudo bash infrastructure/dnsmasq/setup.sh [start|stop|status|test]
#
# Commands:
#   start   — check prerequisites, start dnsmasq in background, self-test
#   stop    — stop the running dnsmasq instance
#   status  — show whether dnsmasq is running and log tail
#   test    — run the 3-stage test sequence from the roadmap
#
# SAFETY RULE (from 2026-09-12 incident):
#   Never point the router's DHCP DNS at 192.168.1.20 until Stage 1 AND
#   Stage 2 of the test sequence both pass here. The script enforces this
#   by printing a clear hold-gate before the Stage 3 instructions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_CONF="${SCRIPT_DIR}/dnsmasq-phase2.conf"
# Deploy to /etc/dnsmasq.d/ so root (dnsmasq) can always read it — the
# project directory may be in a path with spaces or restricted permissions.
CONF_FILE="/etc/dnsmasq.d/parental-safety-phase2.conf"
LOG_DIR="/var/log/parental-safety"
LOG_FILE="${LOG_DIR}/dnsmasq.log"
PID_FILE="/run/parental-safety-dnsmasq.pid"
LISTEN_IP="192.168.1.20"
LISTEN_PORT="53"

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()     { echo -e "${RED}[ERROR]${NC} $*" >&2; }
divider() { echo "────────────────────────────────────────────────────────────"; }

# ── root check ────────────────────────────────────────────────────────────────
require_root() {
    if [[ $EUID -ne 0 ]]; then
        err "This command must be run with sudo."
        exit 1
    fi
}

# ── prerequisite checks ───────────────────────────────────────────────────────
check_dnsmasq_installed() {
    if ! command -v dnsmasq &>/dev/null; then
        err "dnsmasq is not installed. Install it with: sudo apt install dnsmasq"
        exit 1
    fi
    local ver
    ver=$(dnsmasq --version 2>&1 | head -1)
    info "dnsmasq found: ${ver}"
}

check_port_free() {
    info "Checking port ${LISTEN_PORT} on ${LISTEN_IP}..."
    if ss -lnup "sport = :${LISTEN_PORT}" 2>/dev/null | grep -q "${LISTEN_IP}"; then
        err "Port ${LISTEN_PORT} is already in use on ${LISTEN_IP}."
        err "Run 'ss -lnup sport = :53' to see what's using it."
        exit 1
    fi
    # Also check systemd-resolved on 53 (it binds 0.0.0.0 sometimes)
    if ss -lnup "sport = :${LISTEN_PORT}" 2>/dev/null | grep -qE "0\.0\.0\.0|:::"; then
        warn "Something may be listening on 0.0.0.0:53 — this could conflict."
        warn "If dnsmasq fails to start, run: sudo systemctl stop systemd-resolved"
        warn "or add 'DNSStubListener=no' to /etc/systemd/resolved.conf"
    fi
    info "Port ${LISTEN_PORT} appears free on ${LISTEN_IP}."
}

# ── log directory setup ───────────────────────────────────────────────────────
setup_log_dir() {
    if [[ ! -d "${LOG_DIR}" ]]; then
        mkdir -p "${LOG_DIR}"
        info "Created log directory: ${LOG_DIR}"
    fi
    chmod 777 "${LOG_DIR}"
    touch "${LOG_FILE}"
    chmod 666 "${LOG_FILE}"

    # Ubuntu AppArmor: if dnsmasq profile exists, ensure access to LOG_DIR is allowed
    if [[ -d /etc/apparmor.d/local ]] && command -v apparmor_parser &>/dev/null; then
        local aa_local="/etc/apparmor.d/local/usr.sbin.dnsmasq"
        if ! grep -qs "${LOG_DIR}" "${aa_local}" 2>/dev/null; then
            echo "${LOG_DIR}/ rw," >> "${aa_local}"
            echo "${LOG_DIR}/** rw," >> "${aa_local}"
            apparmor_parser -r /etc/apparmor.d/usr.sbin.dnsmasq 2>/dev/null || true
            info "Added AppArmor exception for ${LOG_DIR}"
        fi
    fi

    info "Log file: ${LOG_FILE}"
}

# ── start / stop ──────────────────────────────────────────────────────────────
cmd_start() {
    require_root
    divider
    info "Starting Phase 2 DNS Observation (dnsmasq)"
    divider

    check_dnsmasq_installed
    check_port_free
    setup_log_dir

    if [[ -f "${SOURCE_CONF}" ]]; then
        cp "${SOURCE_CONF}" "${CONF_FILE}"
        chmod 644 "${CONF_FILE}"
    fi

    # Disable systemd-resolved stub listener so it doesn't
    # intercept DNS on 127.0.0.53 before dnsmasq gets it.
    if [[ -f /etc/systemd/resolved.conf ]]; then
        if ! grep -q "DNSStubListener=no" /etc/systemd/resolved.conf 2>/dev/null; then
            sed -i 's/^#DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf
            grep -q "^DNSStubListener=" /etc/systemd/resolved.conf || \
                echo "DNSStubListener=no" >> /etc/systemd/resolved.conf
            systemctl restart systemd-resolved 2>/dev/null || true
            info "Disabled systemd-resolved stub listener"
        fi
    fi

    # Ensure the dnsmasq systemd unit is installed so it
    # survives reboots and restarts automatically.
    if [[ -f "$INSTALL_ROOT/infrastructure/systemd/dnsmasq.service" ]]; then
        cp "$INSTALL_ROOT/infrastructure/systemd/dnsmasq.service" "$SYSTEMD_DIR/dnsmasq.service"
        systemctl daemon-reload
        systemctl enable dnsmasq 2>/dev/null || true
        systemctl restart dnsmasq 2>/dev/null || true
        info "dnsmasq managed by systemd (restart on failure, boot start)"
    else
        warn "dnsmasq.service not found — falling back to manual start"
        dnsmasq --conf-file="${CONF_FILE}"
        sleep 1
    fi

    if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
        info "dnsmasq started (PID $(cat "${PID_FILE}"))."
    elif systemctl is-active --quiet dnsmasq 2>/dev/null; then
        info "dnsmasq started via systemd."
    else
        err "dnsmasq did not start. Check: journalctl -u dnsmasq -n 30"
        exit 1
    fi

    divider
    info "Self-test: querying @${LISTEN_IP} for example.com..."
    sleep 0.5
    if dig +short @"${LISTEN_IP}" example.com A | grep -qE '^[0-9]+\.[0-9]+'; then
        info "✅  Self-test PASSED — dnsmasq is resolving correctly."
    else
        warn "Self-test returned no A record. Showing log tail:"
        tail -20 "${LOG_FILE}" || true
        err "Stage 1 test FAILED. Do NOT proceed to Stage 2 or 3."
        exit 1
    fi

    divider
    echo ""
    echo "  ✅  Stage 1 complete — dnsmasq is running and resolving on ${LISTEN_IP}:53"
    echo ""
    echo "  Next step (Stage 2 — single device manual override):"
    echo "    On ONE phone or laptop:"
    echo "    → Wi-Fi settings → DNS → manually set to ${LISTEN_IP}"
    echo "    → Browse a few websites"
    echo "    → Run:  parental-monitor-dns tail"
    echo "    → Queries from that device should appear attributed to its device_id"
    echo ""
    echo "  ⚠️  Do NOT touch router DHCP DNS settings until Stage 2 passes."
    divider
}

cmd_stop() {
    require_root
    if systemctl is-active --quiet dnsmasq 2>/dev/null; then
        systemctl stop dnsmasq 2>/dev/null
        rm -f "${PID_FILE}"
        info "dnsmasq stopped via systemd."
    elif [[ -f "${PID_FILE}" ]]; then
        local pid
        pid=$(cat "${PID_FILE}")
        if kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}"
            rm -f "${PID_FILE}"
            info "dnsmasq (PID ${pid}) stopped."
        else
            warn "PID file exists but process is not running. Removing stale PID file."
            rm -f "${PID_FILE}"
        fi
    else
        warn "No PID file at ${PID_FILE} and dnsmasq not managed by systemd."
    fi
}

cmd_status() {
    if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
        info "dnsmasq is RUNNING (PID $(cat "${PID_FILE}"))."
    else
        warn "dnsmasq is NOT running."
    fi
    echo ""
    if [[ -f "${LOG_FILE}" ]]; then
        echo "Last 20 log lines:"
        tail -20 "${LOG_FILE}"
    else
        echo "No log file yet at ${LOG_FILE}"
    fi
}

cmd_test() {
    divider
    echo "Phase 2 DNS Observation — 3-Stage Test Sequence"
    divider
    echo ""
    echo "Stage 1 — Ubuntu self-test:"
    echo "  dig @${LISTEN_IP} example.com"
    dig +short @"${LISTEN_IP}" example.com A || true
    echo ""
    echo "Stage 2 — instructions printed during 'start'."
    echo "Stage 3 — only after Stage 1 + 2 pass:"
    echo ""
    echo "  BEFORE touching the router, write down these values:"
    echo "  Router: http://192.168.1.1 → Settings → Network → DNS"
    echo "  Current DNS:  (write it down)"
    echo "  Current DNS2: (write it down)"
    echo ""
    echo "  Then set:"
    echo "  DNS:  ${LISTEN_IP}"
    echo "  DNS2: 8.8.4.4   ← fallback so browsing never dies if dnsmasq stops"
    echo ""
    echo "  To REVERT instantly: set DNS back to 192.168.1.1 (router's own relay)"
    divider
}

# ── main ──────────────────────────────────────────────────────────────────────
COMMAND="${1:-help}"
case "${COMMAND}" in
    start)  cmd_start ;;
    stop)   cmd_stop ;;
    status) cmd_status ;;
    test)   cmd_test ;;
    *)
        echo "Usage: sudo bash setup.sh [start|stop|status|test]"
        exit 1
        ;;
esac
