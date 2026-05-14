# Kalshi · Pit Wall

A cinematic, F1-broadcast-inspired live telemetry dashboard for the Kalshi
agentic trading system.

The page opens with a letterboxed black frame, a red horizon line widens across
the screen, the **KALSHI · PIT WALL** ident lands with HUD vitals, and then the
broadcast HUD takes over: scrolling market tape, driver-cluster portfolio
readouts, race-livery position cards, RPM-arc probability gauge, judge lower-third
ruling, pit-radio memory feed, and a session leaderboard.

Everything reads live from the existing SQLite at `data/trades.db`.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  React + Vite + TS + Tailwind + Framer Motion (5173)     │  ← cinematic HUD
│              ↓ /api/snapshot every ~2.5s                  │
│  FastAPI backend (8765)                                   │  ← reads SQLite
│              ↓                                            │
│  data/trades.db  (trades, positions, sessions,            │
│                   decision_audits, lessons)               │
└──────────────────────────────────────────────────────────┘
```

The backend is a single file (`dashboard/backend/server.py`) that defensively
reads from the SQLite, gracefully handles a missing or schema-less DB, and
exposes one endpoint that returns a snapshot of everything the dashboard needs.

The frontend is a Vite app with all visuals built from CSS, SVG, and Framer
Motion — no chart libraries, no images. The cinematic feel comes from:

- **Letterbox intro** with red horizon line, identifier reveal, vitals snap-in.
- **Broadcast scanlines** + flicker overlays.
- **Race livery** stripes on position cards.
- **HUD chrome** corner brackets on every panel.
- **Marquee tickers** for markets and trades.
- **RPM-style probability arc** with color band shifts.
- **Lower-third judge ruling** that slides in on new decisions.
- **Pit-radio memory feed** with fade-in lesson recall.
- **Driver-cluster portfolio** with tweened numbers and a drawdown bar.

## Running

```bash
# From the repo root:
bash dashboard/run.sh
```

That single command will:

1. Install `fastapi` + `uvicorn` (backend) if needed.
2. Install `npm` deps for the frontend if needed.
3. Start the backend on **http://localhost:8765**.
4. Start the Vite dev server on **http://localhost:5173** and open it.

Vite is configured to proxy `/api/*` to the backend, so there is no CORS work
to do.

### Manual

```bash
# Backend only
pip install -r dashboard/backend/requirements.txt
PYTHONPATH=. uvicorn dashboard.backend.server:app --reload --port 8765

# Frontend only
cd dashboard/frontend
npm install
npm run dev
```

### Production build

```bash
cd dashboard/frontend
npm run build
npm run preview         # serves dist/ on :4173
```

## Data sources

The backend reads these tables when present:

| Table              | Used for                                |
| ------------------ | --------------------------------------- |
| `performance_metrics` | Balance, P&L, drawdown, Sharpe       |
| `trades`           | Trades tape, hit rate fallback          |
| `positions`        | Position cards                          |
| `trading_sessions` | Session leaderboard                     |
| `decision_audits`  | Judge lower-third, calibrated p         |
| `lessons`          | Memory pit-radio feed                   |
| `market_snapshots` | Top scrolling markets ticker            |

Missing tables degrade gracefully — the dashboard renders a **STANDBY** banner
and continues polling.

## Customizing

- **Colors / fonts** — `dashboard/frontend/tailwind.config.js` and
  `dashboard/frontend/src/styles/index.css`.
- **Intro length** — phases in
  `dashboard/frontend/src/components/IntroSequence.tsx`.
- **Polling interval** — argument to `useTelemetry(2500)` in `App.tsx`.
- **Layout** — column spans in `App.tsx`.

## Notes

- The dashboard is read-only. There are no controls that mutate trading state.
- All animations respect `prefers-reduced-motion` indirectly via Framer Motion
  defaults; reduced-motion users still see static panels.
- The Vite dev server hot-reloads; the FastAPI `--reload` flag is enabled so
  edits to `server.py` take effect immediately.
