# Parental Safety Platform — Threat Model (Section 38)

## 1. System Context & Assets Protected

The Parental Safety Platform is a local-first network observer providing non-blocking visibility into device activity and safety risks across a home local area network (LAN).

### Primary Assets & Sensitivity:
1. **Network Telemetry & Activity Logs**: Complete history of DNS requests and IP/MAC mappings across home devices. Highly private personal information.
2. **Device Identity & Behavioral Attribution**: Links between physical hardware, randomized MAC addresses, friendly names, and observed children.
3. **Safety Alert State**: Active and historic records of flagged unsafe content, gambling, phishing lures, and DoH bypass attempts.
4. **Classification Engine Rules & Parent Overrides**: Whitelists, blacklists, category mappings, and administrative exceptions.
5. **DNS Observation Infrastructure**: `dnsmasq` service, packet capture socket, and SQLite database integrity.

---

## 2. Threat Actor Personas & Motivations

| Persona | Technical Skill | Access Level | Primary Motivation |
| :--- | :--- | :--- | :--- |
| **Curious / Evasive Child** | Low to High | Local LAN client (WiFi/Ethernet) | Evade DNS observation, access restricted categories (adult, gaming, social media), conceal active hours. |
| **Compromised LAN Host** | High (Automated) | Local LAN device (IoT, infected PC) | ARP spoofing, DNS cache poisoning, data exfiltration, lateral movement, DoS against observer. |
| **Rogue Guest / Untrusted Device** | Medium | Local LAN guest access | Tamper with platform configuration, dismiss alerts, modify classifications, brute-force admin credentials. |
| **External Internet Adversary** | High | External (WAN) | Port scans, remote code execution, exploiting unpatched services (if router port-forwarded). |

---

## 3. Subsystem Attack Surface & Defense Matrix

### A. Network & DNS Ingestion Subsystem (Phases 1 & 2)

* **Threat A1: Encrypted DNS (DoH / DoT) Bypass**
  * *Attack Vector*: Child configures browser or OS to use DNS-over-HTTPS (e.g. Cloudflare `1.1.1.1` or Google `8.8.8.8`), bypassing port 53.
  * *Platform Defense*: 
    - Phase 2 & 6 detection flags bootstrap queries to known DoH providers (`cloudflare-dns.com`, `dns.google`, etc.).
    - Generates `BYPASS_ATTEMPT` alerts with `HIGH` severity.
    - Observes missing queries relative to ARP presence (`PARTIAL` visibility attribution warning).

* **Threat A2: MAC Address Randomization (Privacy Features)**
  * *Attack Vector*: iOS Private Wi-Fi Address or Android Randomized MAC generates a new MAC address periodically or per-SSID to evade device profiling.
  * *Platform Defense*:
    - Phase 1 MAC Randomization Detector checks the Locally Administered Address (LAA) bit (bit 1 of first octet).
    - Automatically tags device with `mac_is_randomized = 1` and tracks multi-IP address associations via `device_addresses`.

* **Threat A3: ARP Spoofing / Man-in-the-Middle**
  * *Attack Vector*: Compromised machine poisons ARP cache to intercept LAN traffic before it reaches the observer or router.
  * *Platform Defense*:
    - The platform operates strictly in passive observation mode on its own interface.
    - Systemd and operational guidelines mandate static ARP entries on the observer host and router isolation.

---

### B. Database & Storage Subsystem (Phases 4 & 7)

* **Threat B1: Database File Corruption or Locking**
  * *Attack Vector*: High query volume from multiple devices causes SQLite database locking (`sqlite3.OperationalError: database is locked`).
  * *Platform Defense*:
    - SQLite WAL (Write-Ahead Logging) mode enabled (`PRAGMA journal_mode=WAL;`).
    - Busy timeout configured to 5000ms (`PRAGMA busy_timeout=5000;`).
    - Foreign key constraints enforced (`PRAGMA foreign_keys=ON;`).

* **Threat B2: Unauthorized Data Exfiltration**
  * *Attack Vector*: Rogue client downloads complete DNS query history via export API.
  * *Platform Defense*:
    - Phase 10 authentication and rate limiting restrict data exports.
    - All data exports trigger tamper-evident entries in `audit_logs`.
    - Mandatory ethical labels (Sections 11 & 34) prevent misrepresenting raw packet timestamps as continuous screen time.

---

### C. FastAPI Backend & REST API Subsystem (Phases 3, 5, 6, 9, 10)

* **Threat C1: Brute-Force Authentication Attacks**
  * *Attack Vector*: Script attempts automated password guessing against `POST /api/auth/login`.
  * *Platform Defense*:
    - Sliding-window rate limiter restricts `/api/auth/login` to **5 requests per minute** per IP.
    - Returns `HTTP 429 Too Many Requests` with `Retry-After: 60` headers.
    - Every failed attempt logs `AUTH_LOGIN_FAILED` with the attacker's IP to `audit_logs`.

* **Threat C2: Cross-Site Request Forgery (CSRF)**
  * *Attack Vector*: Child or malicious webpage tricks parent's browser into executing an unauthorized classification override or alert dismissal.
  * *Platform Defense*:
    - `SecurityMiddleware` verifies `Origin` and `Referer` headers on all mutating verbs (`POST`, `PUT`, `PATCH`, `DELETE`).
    - Session cookies use `SameSite=Lax` and `HttpOnly`.

* **Threat C3: Clickjacking & MIME-Sniffing**
  * *Platform Defense*:
    - `X-Frame-Options: DENY` prevents framing in malicious iframes.
    - `X-Content-Type-Options: nosniff` stops MIME type sniffing.
    - `Referrer-Policy: strict-origin-when-cross-origin`.

---

### D. React Dashboard & WebSockets Subsystem (Phases 8 & 9)

* **Threat D1: WebSocket Denial of Service (Connection Flooding)**
  * *Attack Vector*: Malicious client opens hundreds of concurrent WebSocket connections to exhaust server file descriptors.
  * *Platform Defense*:
    - ConnectionManager bounds client tracking with disconnect garbage collection.
    - Client heartbeats require periodic `ping` frames; dead sockets are pruned on failed write.
    - IP rate limiting applies across all `/api/` endpoints.

---

## 4. Tamper-Evident Audit Logging

Every state-changing administrative action is permanently recorded in the `audit_logs` table:

```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor_ip TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    details TEXT
);
```

### Audited Actions:
- `AUTH_LOGIN_SUCCESS` / `AUTH_LOGIN_FAILED`
- `AUTH_LOGOUT`
- `DEVICE_UPDATE` (Friendly name or classification changed)
- `ALERT_STATUS_UPDATE` (Alert acknowledged, dismissed, or resolved)
- `CATEGORY_OVERRIDE` (Domain manually assigned to a different safety category)
- `DATA_EXPORT` (CSV or JSON dataset exported)

---

## 5. Residual Risks & Operational Hardening Checklist

1. **Local Physical Access**: If an attacker has physical root access to the Raspberry Pi / observer machine, local SQLite databases can be read directly.
   - *Recommendation*: Use Linux full-disk encryption (LUKS) on the observer storage drive.
2. **Hardcoded Gateway Direct Queries**: If a device hardcodes DNS lookups directly to an external IP (`8.8.8.8:53`) bypassing local DHCP DNS settings:
   - *Recommendation*: Add router firewall rule (iptables/nftables) redirecting all outgoing port 53 UDP/TCP traffic to the observer:
     ```bash
     iptables -t nat -A PREROUTING -p udp --dport 53 -j DNAT --to 192.168.1.20:53
     ```
3. **Collector Privilege Separation (Phase 11)**:
   - Transitioning `parental-monitor-dns` off `sudo` entirely using Linux file capabilities:
     ```bash
     sudo setcap 'cap_net_raw,cap_net_admin+ep' collector/.venv/bin/python
     ```
