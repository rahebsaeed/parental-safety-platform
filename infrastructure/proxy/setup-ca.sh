#!/usr/bin/env bash
# =============================================================================
# setup-ca.sh — Create the parental web-proxy Certificate Authority.
#
# Generates a private CA (10-year validity) in mitmproxy's on-disk layout:
#   <CA_DIR>/mitmproxy-ca.pem       — private key + certificate (0600, server only)
#   <CA_DIR>/mitmproxy-ca-cert.pem  — public certificate (0644, safe to
#                                      distribute to supervised devices)
#   <CA_DIR>/mitmproxy-ca-cert.p12  — PKCS#12 bundle for iOS/Windows import
#
# The .pem CERT (never the key) is served by GET /api/proxy/ca.pem for
# installation. Idempotent: existing CA is kept.
#
# Usage: sudo ./infrastructure/proxy/setup-ca.sh [CA_DIR]
# =============================================================================
set -euo pipefail

CA_DIR="${1:-/opt/parental-safety/proxy/ca}"
SERVICE_USER="parental-monitor"
SERVICE_GROUP="parental-monitor"

[[ "$EUID" -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }
command -v openssl &>/dev/null || { echo "openssl is required" >&2; exit 1; }

mkdir -p "$CA_DIR"

if [[ -f "$CA_DIR/mitmproxy-ca.pem" && -f "$CA_DIR/mitmproxy-ca-cert.pem" ]]; then
    echo "[setup-ca] CA already exists in $CA_DIR — keeping it."
    echo "  Fingerprint: $(openssl x509 -noout -fingerprint -sha256 -in "$CA_DIR/mitmproxy-ca-cert.pem" 2>/dev/null || echo unknown)"
    exit 0
fi

echo "[setup-ca] Generating parental CA (10 years) in $CA_DIR..."
TMP_KEY="$CA_DIR/.ca-key.tmp"
trap 'rm -f "$TMP_KEY"' EXIT

openssl genrsa -out "$TMP_KEY" 4096 2>/dev/null
openssl req -x509 -new -nodes \
    -key "$TMP_KEY" \
    -sha256 -days 3650 \
    -subj "/CN=Parental Safety Web Filter CA/O=Home LAN/C=MA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign,digitalSignature" \
    -out "$CA_DIR/mitmproxy-ca-cert.pem" 2>/dev/null

# mitmproxy layout: key + cert concatenated in mitmproxy-ca.pem
cat "$TMP_KEY" "$CA_DIR/mitmproxy-ca-cert.pem" > "$CA_DIR/mitmproxy-ca.pem"
rm -f "$TMP_KEY"
trap - EXIT

# PKCS#12 bundle (empty password) for iOS / Windows import wizards
openssl pkcs12 -export -out "$CA_DIR/mitmproxy-ca-cert.p12" \
    -inkey "$CA_DIR/mitmproxy-ca.pem" \
    -in "$CA_DIR/mitmproxy-ca-cert.pem" \
    -passout pass: 2>/dev/null || true
# DER (.cer) variant for Android
openssl x509 -in "$CA_DIR/mitmproxy-ca-cert.pem" -outform DER \
    -out "$CA_DIR/mitmproxy-ca-cert.cer" 2>/dev/null || true

chown -R "$SERVICE_USER:$SERVICE_GROUP" "$CA_DIR"
chmod 700 "$CA_DIR"
chmod 600 "$CA_DIR/mitmproxy-ca.pem"
chmod 644 "$CA_DIR/mitmproxy-ca-cert.pem" "$CA_DIR/mitmproxy-ca-cert.p12" "$CA_DIR/mitmproxy-ca-cert.cer" 2>/dev/null || true

echo "[setup-ca] Done."
echo "  Fingerprint: $(openssl x509 -noout -fingerprint -sha256 -in "$CA_DIR/mitmproxy-ca-cert.pem")"
echo "  Install the CERT (never the key) on each supervised device,"
echo "  then point that device's Wi-Fi proxy at 192.168.1.20:8080."
