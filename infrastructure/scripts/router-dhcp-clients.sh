#!/usr/bin/env bash
# =============================================================================
# router-dhcp-clients.sh — Get current DHCP clients from D-Link router
# =============================================================================
ROUTER="${ROUTER_BASE_URL:-http://192.168.1.1}"
USER="${ROUTER_USER:-user}"
PWD_HASH="${ROUTER_PWD_HASH:-ee11cbb19052e40b07aac0ca060c23ee}"

# Login and get cookies
curl -s -c /tmp/dlink_cookies.txt \
  "${ROUTER}/cgi-bin/Login.asp?User=${USER}&Pwd=${PWD_HASH}&_=$(date +%s%3N)" \
  -H "x-requested-with: XMLHttpRequest" -H "accept: */*" >/dev/null 2>&1

# Get DHCP client list
curl -s -b /tmp/dlink_cookies.txt \
  "${ROUTER}/cgi-bin/get/New_GUI/home_getclientList.asp?_=$(date +%s%3N)" \
  -H "accept: */*" -H "x-requested-with: XMLHttpRequest" 2>&1
