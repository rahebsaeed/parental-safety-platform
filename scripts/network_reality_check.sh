#!/usr/bin/env bash
#
# Network Reality Check
#
# Read-only reconnaissance of THIS machine's network configuration.
# Does not touch the router, does not send an active ARP scan, does not
# change any configuration. See docs/networking/network-reality-check.md
# for how to interpret the output.
#
# Run this on your actual Ubuntu machine on your home network — running it
# anywhere else (a cloud VM, a container without host networking) will just
# describe that environment instead.

set -euo pipefail

# Always operate from the repository root, regardless of where this script
# is invoked from. Without this, running it via a different relative path
# (or from inside collector/) would scatter the report file wherever the
# shell's cwd happened to be instead of a predictable location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUTFILE="reality-check-${TIMESTAMP}.txt"

run_section() {
    local title="$1"
    shift
    {
        echo "=================================================="
        echo "== ${title}"
        echo "== Command: $*"
        echo "=================================================="
        if command -v "$1" >/dev/null 2>&1; then
            "$@" 2>&1 || echo "(command exited non-zero, output above if any)"
        else
            echo "(command not found: $1)"
        fi
        echo
    } | tee -a "$OUTFILE"
}

# Truncate/create the file fresh
: > "$OUTFILE"

echo "Writing report to ${OUTFILE}"
echo

run_section "Interfaces and addresses"      ip addr show
run_section "Routing table"                 ip route show
run_section "IPv4 neighbor cache"           ip neigh show
run_section "IPv6 neighbor cache"           ip -6 neigh show
run_section "systemd-resolved status"       resolvectl status
run_section "NetworkManager device status"  nmcli device status
run_section "resolv.conf"                   cat /etc/resolv.conf
run_section "Active NetworkManager connections" nmcli connection show --active

# nmcli device show needs an interface name; try to infer the default one
DEFAULT_IFACE="$(ip route show default 2>/dev/null | awk '/default/ {for(i=1;i<=NF;i++) if ($i=="dev") print $(i+1)}' | head -n1 || true)"
if [ -n "${DEFAULT_IFACE:-}" ]; then
    run_section "NetworkManager detail for ${DEFAULT_IFACE}" nmcli device show "$DEFAULT_IFACE"
else
    {
        echo "=================================================="
        echo "== Could not auto-detect default interface for 'nmcli device show'"
        echo "== Run manually: nmcli device show <iface>"
        echo "=================================================="
        echo
    } | tee -a "$OUTFILE"
fi

echo "Done. Report saved to: $(pwd)/${OUTFILE}"
echo "Read docs/networking/network-reality-check.md for how to interpret it."
