#!/usr/bin/env bash
# =============================================================================
# router-dns-revert-check.sh — 3-hour Safe-DNS failsafe (the ONLY automation
# that may change router DNS over HTTP).
#
# Manual model: the parent enables filtered DNS from the dashboard
# (POST /api/router-dns/mode {"mode":"dnsmasq"}), which writes a deadline
# file. This checker runs every 5 min via parental-monitor-dns-revert.timer:
#   - no deadline file   → nothing to do (router stays as-is)
#   - deadline in future → nothing to do
#   - deadline passed    → router-dns.sh off (back to 192.168.1.1) + clear file
#
# Safe to run any time; never fails hard (timer must stay green). Supports
#   --dry-run  print what would happen, change nothing
# Env overrides: ROUTER_DNS_DEADLINE_FILE, ROUTER_DNS_SWITCH_SCRIPT.
# =============================================================================
set -u

DEADLINE_FILE="${ROUTER_DNS_DEADLINE_FILE:-/var/lib/parental-safety/router-dns-deadline}"
SWITCH_SCRIPT="${ROUTER_DNS_SWITCH_SCRIPT:-/opt/parental-safety/scripts/router-dns.sh}"
DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
fi

log() { echo "[router-dns-revert] $*"; }

if [[ ! -f "$DEADLINE_FILE" ]]; then
    log "no deadline file — nothing to do"
    exit 0
fi

EXPIRES="$(head -n 1 "$DEADLINE_FILE" 2>/dev/null | tr -d ' \t\r\n' || echo "")"
if ! [[ "$EXPIRES" =~ ^[0-9]+$ ]] || [[ "$EXPIRES" -le 0 ]]; then
    log "invalid deadline content — clearing stale file"
    if [[ "$DRY_RUN" -eq 1 ]]; then exit 0; fi
    rm -f "$DEADLINE_FILE" 2>/dev/null || true
    exit 0
fi

NOW="$(date +%s)"
if [[ "$NOW" -lt "$EXPIRES" ]]; then
    REMAIN=$((EXPIRES - NOW))
    log "deadline in future (${REMAIN}s remaining) — nothing to do"
    exit 0
fi

log "deadline passed (expired $(date -u -d "@$EXPIRES" '+%F %T UTC' 2>/dev/null || echo "$EXPIRES")) — reverting router DNS to default"
if [[ "$DRY_RUN" -eq 1 ]]; then
    log "[dry-run] would run: $SWITCH_SCRIPT off && rm -f $DEADLINE_FILE"
    exit 0
fi

if [[ ! -x "$SWITCH_SCRIPT" ]]; then
    # Dev/repo fallback: same tree's router-dns.sh next to this script.
    HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -x "$HERE/router-dns.sh" ]]; then
        SWITCH_SCRIPT="$HERE/router-dns.sh"
    else
        log "ERROR: switch script not executable: $SWITCH_SCRIPT (router left as-is, deadline kept for retry)"
        exit 0
    fi
fi

if "$SWITCH_SCRIPT" off 2>&1 | tail -n 5; then
    log "router DNS reverted to default (192.168.1.1)"
else
    log "revert command failed — deadline kept so the next tick retries"
    exit 0
fi
rm -f "$DEADLINE_FILE" 2>/dev/null || true
log "deadline cleared"
exit 0
