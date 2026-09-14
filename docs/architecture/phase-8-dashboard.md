# Phase 8 — React Dashboard Architecture

## 1. Overview & Objective
Phase 8 delivers an enterprise-grade, responsive single-page application (SPA) built with **React 19**, **TypeScript**, and **Vite**, using a bespoke **Vanilla CSS design system** that avoids generic component frameworks.

The dashboard integrates with all backend REST endpoints (`/api/health`, `/api/devices`, `/api/activity`, `/api/alerts`, `/api/analytics`, `/api/classifications`) and visualizes real-time network safety telemetry captured by the local DNS observer daemon.

---

## 2. Technical Stack & File Structure

```
frontend/
├── index.html                 # App shell with Google Fonts (Outfit, Inter)
├── package.json               # React 19, Lucide React, TypeScript, Vite
├── tsconfig.json              # Strict TS bundler configuration
├── vite.config.ts             # Dev proxy (/api -> http://127.0.0.1:8000)
├── src/
│   ├── index.css              # Custom Vanilla CSS tokens, glassmorphism & resets
│   ├── main.tsx               # React 19 DOM entry point
│   ├── App.tsx                # Main view router, global health poll & refresh coordinator
│   ├── types/
│   │   └── api.ts             # TypeScript interfaces mirroring FastAPI Pydantic schemas
│   ├── services/
│   │   └── api.ts             # Centralized Fetch API client with error normalization
│   ├── components/
│   │   ├── Header.tsx         # Live observer status badge with pulse & manual refresh
│   │   ├── Sidebar.tsx        # Navigation sidebar with alert badge counter
│   │   └── EthicalBanner.tsx  # Sections 11 & 34 mandatory ethical disclaimer
│   └── pages/
│       ├── OverviewPage.tsx   # Executive summary: stats cards, category bars, recent queries
│       ├── DevicesPage.tsx    # Discovered devices grid, randomized MAC indicators, rename modal
│       ├── AlertsPage.tsx     # Advisory safety console: triage actions, explainability cards
│       ├── ActivityPage.tsx   # Filterable DNS stream: search, device filter, visibility badges
│       ├── AnalyticsPage.tsx  # 24h active hours histogram, category breakdown, CSV/JSON export
│       └── ClassificationsPage.tsx # Domain directory, live classifier sandbox, override modal
```

---

## 3. Design System & Aesthetics

1. **Dark Theme Canvas**: Rich `#090d16` canvas with radial gradient backdrops (`rgba(99, 102, 241, 0.08)` and `rgba(14, 165, 233, 0.06)`).
2. **Glassmorphism**: Translucent cards (`rgba(26, 34, 52, 0.75)`) with backdrop blur (`16px`) and subtle borders (`rgba(255, 255, 255, 0.07)`).
3. **Category Color Palette**: Consistent tokens aligned with the Phase 5 engine:
   - Social Media: `#e91e8c`
   - Streaming: `#e53935`
   - Gaming: `#9333ea`
   - Education: `#2563eb`
   - Productivity: `#0891b2`
   - Adult/Explicit: `#dc2626`
   - Advertising/Tracking: `#ea580c`
   - Infrastructure/System: `#475569`
4. **Live Daemon Status Pulse**: Pulsing green dot indicator reflecting `dns_daemon_alive` from the background collector process.

---

## 4. Key Page Capabilities

### Overview Page
- At-a-glance KPI metrics: Total queries, distinct domains, active devices, and top category.
- Top categories visual percentage bars with color-coded badges.
- Recent 8 DNS queries with real-time visibility indicators.
- Quick navigation shortcuts into individual consoles.

### Devices Page
- Discovered devices grid with hardware classification icons (Smartphone, Laptop, Router, etc.).
- Direct indicator for **Randomized MAC** addresses (LAA bit 1 set) vs. hardware manufacturer OUIs.
- Inline rename modal to assign friendly names (e.g., "Maya's Phone") and device classifications.
- Full address history inspection drawer showing past observed IPs, MACs, and hostnames.

### Safety Alerts Console
- Severity filtering (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) and status triage (`ACTIVE`, `ACKNOWLEDGED`, `DISMISSED`, `RESOLVED`).
- Explainability cards detailing:
  - Human-readable title and description
  - Exact rule matched (`EXACT_MATCH`, `DOMAIN_SUFFIX`, `KEYWORD_REGEX`)
  - Full parent explanation and recommended conversational guidance
  - Occurrence aggregation count and timestamps.
- "Run Safety Scan" action button to trigger real-time query scanning against the detection rules.

### Activity Stream
- Filterable DNS query log by domain substring, device ID, visibility mode (`FULL` vs. `PARTIAL`), and response status.
- Pagination controls with configurable limit (25, 50, 100).
- Visual status badges (`NOERROR` green, `NXDOMAIN` amber, `SERVFAIL` red).

### Network-Derived Analytics
- Mandatory Sections 11 & 34 ethical disclaimer permanently anchored at the top:
  > *"Network-derived indicator of DNS request activity. DNS queries do not represent active screen time, user attention, or app foreground duration."*
- **24-Hour Active Hours Histogram (00:00 - 23:00)**: Visual bar representation of query density across the day.
- **Category Share Progress Bars**: Percentage calculation per category.
- **14-Day Query Volume Trend**: Historical query patterns.
- **Data Export**: Direct CSV and JSON streaming exports with ethics headers.

### Domain Rules & Classifications
- Comprehensive directory of categorized domains.
- **Live Classifier Sandbox**: Real-time evaluation input allowing parents/admins to type any domain (e.g. `discord.gg`, `tiktok.com`) and immediately inspect how the rule engine categorizes it.
- **Parent Override Modal**: Allows reclassifying any domain to an alternate category with an optional rationale note.
- **Batch Sync Button**: Runs automated classification against any unclassified domains in the database.

---

## 5. Verification & Build
The frontend is compiled using standard production bundling:
```bash
cd frontend
npm run build
```
Result: 0 TypeScript compile errors, producing optimized chunks in `frontend/dist/`.
