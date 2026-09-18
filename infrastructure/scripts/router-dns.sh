#!/usr/bin/env bash
# =============================================================================
# router-dns.sh — Automatically switch router DNS between 192.168.1.20
#                   (dnsmasq, PC on) and 192.168.1.1 (router, PC off)
# =============================================================================# Usage:
#   sudo ./router-dns.sh on    → Set router DNS to 192.168.1.20 (dnsmasq on)
#   sudo ./router-dns.sh off   → Set router DNS to 192.168.1.1 (router)
#   sudo ./router-dns.sh status → Show current router DNS setting
# =============================================================================
set -euo pipefail

# All overridable via environment (ROUTER_BASE_URL/ROUTER_USER/
# ROUTER_PWD_HASH); defaults are the D-Link factory credentials and this
# network's addresses, matching the backend API defaults.
ROUTER="${ROUTER_BASE_URL:-http://192.168.1.1}"
DNS_ON="192.168.1.20"
DNS_OFF="192.168.1.1"
USER="${ROUTER_USER:-user}"
PWD_HASH="${ROUTER_PWD_HASH:-ee11cbb19052e40b07aac0ca060c23ee}"
# Short DHCP lease (seconds) enforced on every switch. With 600s, clients
# renew (T1) every ~5 min, so any router-DNS switch propagates LAN-wide
# within minutes — no router reboot needed per switch. (The factory 86400s
# lease meant up to 24h of split visibility after each change.)
DHCP_LEASE="${ROUTER_DHCP_LEASE:-600}"

login() {
  curl -s -c /tmp/dlink_cookies.txt \
    "${ROUTER}/cgi-bin/Login.asp?User=${USER}&Pwd=${PWD_HASH}&_=$(date +%s%3N)" \
    -H "x-requested-with: XMLHttpRequest" \
    -H "accept: */*" \
    2>/dev/null || echo ""
}

get_session_key() {
  local key
  key=$(curl -s -b /tmp/dlink_cookies.txt \
    "${ROUTER}/cgi-bin/get/New_GUI/get_sessionKey.asp?_=$(date +%s%3N)" \
    -H "accept: */*" \
    -H "x-requested-with: XMLHttpRequest" \
    2>/dev/null | tr -d '\n')
  echo "$key"
}

set_router_dns() {
  local dns_ip="$1"
  local session_key
  session_key=$(get_session_key)

  if [ -z "$session_key" ]; then
    echo "ERROR: Could not get session key from router"
    exit 1
  fi

  echo "Session key: $session_key"
  echo "Setting router DNS to $dns_ip..."

  curl -s -b /tmp/dlink_cookies.txt \
    "${ROUTER}/cgi-bin/New_GUI/Set/Network.asp" \
    -H "accept: */*" \
    -H "accept-language: en-US,en;q=0.7" \
    -H "content-type: application/x-www-form-urlencoded; charset=UTF-8" \
    -H "x-requested-with: XMLHttpRequest" \
    -H "referer: ${ROUTER}/cgi-bin/New_GUI/Network.asp" \
    --data-binary "lan_ip1=192.168.1.1&lan_netmask1=255.255.255.0&lan_dhcp_type=1&lan_dhcp_start=192.168.1.2&lan_dhcp_count=253&lan_dhcp_lease=${DHCP_LEASE}&lan_dhcp_option60_vendorID=MSFT+5.0&lan_dhcp_relay_server=&upnp_active=Yes&mirror_active=No&AutoConfig_Flag=1&RAEnable_Flag=1&RAMode=0&radvdPrefix=3ffe%3A501%3Affff%3A100%3A%3A&RAPrefixLen=64&PreferredLifetime=3600&ValidLifetime=7200&RAManagedEn_Flag=0&RAOtherEn_Flag=1&rapdsource=0&EnDHCPServerFlag=1&DHCPSetTypeFlag=0&AddrFormat=AddrPool&dhcpPrefix=&PrefixLen=&t1=3600&t2=7200&DnsSrvOne=fe80%3A%3A1&DnsSrvTwo=fe80%3A%3A2&DnsSrvOne_Source=fe80%3A%3A1&DnsSrvTwo_Source=fe80%3A%3A2&dnssource=999&pridns=${dns_ip}&secdns=${dns_ip}&sessionKey=${session_key}" \
    2>/dev/null || echo "FAILED"

  echo "Router DNS set to $dns_ip"
}

case "${1:-}" in
  on)
    echo "=== Setting DNS to dnsmasq (PC ON) ==="
    login
    set_router_dns "$DNS_ON"
    ;;
  off)
    echo "=== Setting DNS to router (PC OFF) ==="
    login
    set_router_dns "$DNS_OFF"
    ;;
  *)
    echo "Usage: $0 {on|off}"
    echo "  on   → Set router DNS to 192.168.1.20 (dnsmasq on)"
    echo "  off  → Set router DNS to 192.168.1.1 (router DNS)"
    exit 1
    ;;
esac
