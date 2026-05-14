import {
  Activity,
  AlertTriangle,
  Brain,
  CalendarClock,
  CircleDollarSign,
  Command as CommandIcon,
  Crosshair,
  Cpu,
  DollarSign,
  Eye,
  Gauge,
  Layers3,
  Lock,
  LogOut,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  TrendingUp,
  Wallet,
  X,
  Zap,
} from "lucide-react";
import React, { useEffect, useMemo, useRef, useState } from "react";

const emptyData = {
  summary: null,
  positions: [],
  opportunities: [],
  cycles: [],
  health: null,
  costs: null,
};

const tabs = [
  { id: "overview", label: "Overview", Icon: Activity },
  { id: "opportunities", label: "Opportunities", Icon: Crosshair },
  { id: "positions", label: "Positions", Icon: Wallet },
  { id: "cycles", label: "Cycles", Icon: CalendarClock },
  { id: "costs", label: "Costs", Icon: CircleDollarSign },
];

function authHeader(username, password) {
  return `Basic ${btoa(`${username}:${password}`)}`;
}

async function getJson(path, auth) {
  const res = await fetch(path, {
    headers: { Authorization: auth },
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json();
}

export default function App() {
  const shellRef = useRef(null);
  const [credentials, setCredentials] = useState(() => ({
    username: localStorage.getItem("jj_dashboard_user") || "admin",
    password: "",
  }));
  const [auth, setAuth] = useState(() => sessionStorage.getItem("jj_dashboard_auth") || "");
  const [data, setData] = useState(emptyData);
  const [status, setStatus] = useState({ loading: false, error: "" });
  const [tab, setTab] = useState("overview");
  const [cinemaMode, setCinemaMode] = useState(true);
  const [selectedOpportunityId, setSelectedOpportunityId] = useState("");
  const [commandOpen, setCommandOpen] = useState(false);
  const [motionPaused, setMotionPaused] = useState(false);
  const [introVisible, setIntroVisible] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);

  const isAuthed = Boolean(auth);
  const summary = data.summary || {};
  const pnlClass = (summary.total_pnl || 0) >= 0 ? "positive" : "negative";
  const healthStatus = data.health?.status || "unknown";

  async function load(nextAuth = auth) {
    if (!nextAuth) return;
    setStatus({ loading: true, error: "" });
    try {
      const [summaryPayload, positions, opportunities, cycles, health, costs] = await Promise.all([
        getJson("/api/summary", nextAuth),
        getJson("/api/positions", nextAuth),
        getJson("/api/opportunities", nextAuth),
        getJson("/api/cycles", nextAuth),
        getJson("/api/health", nextAuth),
        getJson("/api/costs", nextAuth),
      ]);
      setData({
        summary: summaryPayload,
        positions: positions.positions || [],
        opportunities: opportunities.opportunities || [],
        cycles: cycles.cycles || [],
        health,
        costs,
      });
      setLastUpdated(new Date());
      setStatus({ loading: false, error: "" });
    } catch (error) {
      setStatus({ loading: false, error: error.message });
    }
  }

  function login(event) {
    event.preventDefault();
    const nextAuth = authHeader(credentials.username, credentials.password);
    localStorage.setItem("jj_dashboard_user", credentials.username);
    sessionStorage.setItem("jj_dashboard_auth", nextAuth);
    setAuth(nextAuth);
    load(nextAuth);
  }

  function logout() {
    sessionStorage.removeItem("jj_dashboard_auth");
    setAuth("");
    setData(emptyData);
  }

  useEffect(() => {
    if (auth) load(auth);
  }, []);

  useEffect(() => {
    if (!introVisible) return undefined;
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const timeout = window.setTimeout(() => setIntroVisible(false), prefersReducedMotion ? 1200 : 8200);
    return () => window.clearTimeout(timeout);
  }, [introVisible]);

  const focusItems = useMemo(() => {
    const opportunities = data.opportunities.map(normalizeOpportunity);
    const positions = data.positions.map(normalizePosition);
    if (opportunities.length) return [...opportunities, ...positions].slice(0, 12);
    return positions.slice(0, 12);
  }, [data.opportunities, data.positions]);

  useEffect(() => {
    if (!focusItems.length) return;
    const stillVisible = focusItems.some((row) => row.id === selectedOpportunityId);
    if (!stillVisible) setSelectedOpportunityId(focusItems[0].id);
  }, [focusItems, selectedOpportunityId]);

  const focusedOpportunity = useMemo(() => {
    return focusItems.find((row) => row.id === selectedOpportunityId) || focusItems[0] || null;
  }, [focusItems, selectedOpportunityId]);

  const tickerItems = useMemo(() => {
    const opportunityItems = focusItems.slice(0, 8).map((row) => ({
      label: row.ticker || "MARKET",
      value: row.type === "position" ? currency(row.unrealized_pnl || 0) : `${number(row.confidence)}% conf`,
      tone: row.signal || "neutral",
    }));
    const cycleItem = {
      label: "P&L",
      value: currency(summary.total_pnl || 0),
      tone: (summary.total_pnl || 0) >= 0 ? "LONG" : "SHORT",
    };
    return [cycleItem, ...opportunityItems];
  }, [focusItems, summary.total_pnl]);

  function handlePointerMove(event) {
    if (!shellRef.current) return;
    const rect = shellRef.current.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = ((event.clientY - rect.top) / rect.height) * 100;
    shellRef.current.style.setProperty("--mx", `${x.toFixed(2)}%`);
    shellRef.current.style.setProperty("--my", `${y.toFixed(2)}%`);
  }

  return (
    <div
      ref={shellRef}
      className={`shell ${cinemaMode ? "cinema-mode" : ""} ${motionPaused ? "motion-paused" : ""}`}
      onPointerMove={handlePointerMove}
    >
      <CinematicBackdrop />

      <aside className="sidebar">
        <div className="brandmark">
          <div className="monogram">J&J</div>
          <div>
            <p>J&J AI Studio</p>
            <span>An AI studio for Main Street, not Silicon Valley.</span>
          </div>
        </div>

        <nav aria-label="Dashboard views">
          {tabs.map(({ id, label, Icon }) => (
            <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
              <Icon size={17} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className={`health ${healthStatus}`}>
          <ShieldCheck size={18} />
          <div>
            <strong>{healthStatus}</strong>
            <span>System health</span>
          </div>
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <p className="eyebrow">Agentic prediction desk</p>
            <h1>Kalshi pit wall cockpit</h1>
          </div>
          <div className="top-actions">
            <button className="ghost-button" onClick={() => setCommandOpen(true)}>
              <Search size={16} />
              Command
            </button>
            <button className="ghost-button" onClick={() => setIntroVisible(true)}>
              <Play size={16} />
              Intro
            </button>
            <button className="ghost-button" onClick={() => setCinemaMode((value) => !value)}>
              {cinemaMode ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
              {cinemaMode ? "Focus" : "Cinematic"}
            </button>
            <button className="refresh" onClick={() => load()} disabled={!isAuthed || status.loading}>
              <RefreshCw size={16} className={status.loading ? "spin" : ""} />
              Refresh
            </button>
            {isAuthed && (
              <button className="icon-button" onClick={logout} aria-label="Lock dashboard">
                <LogOut size={16} />
              </button>
            )}
          </div>
        </header>

        {!isAuthed ? (
          <Login credentials={credentials} setCredentials={setCredentials} login={login} />
        ) : status.error ? (
          <div className="alert">
            <AlertTriangle size={20} />
            <div>
              <strong>Dashboard API unavailable</strong>
              <p>{status.error}</p>
            </div>
          </div>
        ) : (
          <>
            <TickerTape items={tickerItems} paused={motionPaused} />
            {tab === "overview" && (
              <Overview
                summary={summary}
                pnlClass={pnlClass}
                health={data.health}
                opportunities={focusItems}
                positions={data.positions}
                cycles={data.cycles}
                focusedOpportunity={focusedOpportunity}
                setSelectedOpportunityId={setSelectedOpportunityId}
                motionPaused={motionPaused}
                setMotionPaused={setMotionPaused}
                loading={status.loading}
                lastUpdated={lastUpdated}
              />
            )}
            {tab === "opportunities" && (
              <Opportunities
                rows={focusItems}
                focusedOpportunity={focusedOpportunity}
                selectedOpportunityId={selectedOpportunityId}
                setSelectedOpportunityId={setSelectedOpportunityId}
              />
            )}
            {tab === "positions" && <Positions rows={data.positions} />}
            {tab === "cycles" && <Cycles rows={data.cycles} />}
            {tab === "costs" && <Costs costs={data.costs} />}
            <CommandPalette
              open={commandOpen}
              onClose={() => setCommandOpen(false)}
              items={focusItems}
              cycles={data.cycles}
              onSelect={(row) => {
                setSelectedOpportunityId(row.id);
                setTab("opportunities");
                setCommandOpen(false);
              }}
            />
          </>
        )}
      </main>
      {introVisible && <CinematicIntro onSkip={() => setIntroVisible(false)} />}
    </div>
  );
}

function CinematicIntro({ onSkip }) {
  return (
    <section className="intro-cinematic" aria-label="F1-inspired cinematic opening">
      <div className="intro-track" />
      <div className="intro-grain" />
      <div className="intro-scan" />

      <header className="intro-header">
        <div>
          <span>J&J AI Studio</span>
          <strong>Kalshi race control</strong>
        </div>
        <button onClick={onSkip}>Skip to cockpit</button>
      </header>

      <div className="start-light-array" aria-label="Starting lights">
        {["S1", "S2", "S3", "S4", "S5"].map((label) => (
          <span key={label}>
            <i />
            <em>{label}</em>
          </span>
        ))}
      </div>

      <div className="intro-title-block">
        <p>Rosso pit wall sequence</p>
        <h2>Lights out. Market edge in sight.</h2>
        <div className="intro-readouts">
          <span>Race mode: paper</span>
          <span>Signal telemetry online</span>
          <span>Kalshi cockpit loading</span>
        </div>
      </div>

      <div className="formula-car-wrap" aria-hidden="true">
        <div className="speed-trails" />
        <div className="formula-car">
          <span className="front-wing" />
          <span className="nose" />
          <span className="cockpit" />
          <span className="halo" />
          <span className="engine-cover" />
          <span className="sidepod" />
          <span className="rear-wing" />
          <span className="wheel wheel-front" />
          <span className="wheel wheel-rear" />
          <span className="floor" />
        </div>
      </div>

      <div className="intro-cockpit-preview">
        <div>
          <span>P&L</span>
          <strong>$0.25</strong>
        </div>
        <div>
          <span>Focus</span>
          <strong>NFL-CHIEFS-SUN</strong>
        </div>
        <div>
          <span>Health</span>
          <strong>Degraded</strong>
        </div>
      </div>
    </section>
  );
}

function CinematicBackdrop() {
  return (
    <div className="cinematic-backdrop" aria-hidden="true">
      <div className="photo-layer" />
      <div className="light-sweep" />
      <div className="grid-layer" />
      <div className="noise-layer" />
    </div>
  );
}

function Login({ credentials, setCredentials, login }) {
  return (
    <section className="login-panel">
      <div className="login-copy">
        <div className="login-lock">
          <Lock size={22} />
        </div>
        <p className="eyebrow">Private access</p>
        <h2>J&J AI Studio trading command</h2>
        <p>Railway-protected dashboard access for the Kalshi agentic system.</p>
      </div>
      <form onSubmit={login}>
        <label>
          Username
          <input
            value={credentials.username}
            onChange={(event) => setCredentials({ ...credentials, username: event.target.value })}
            autoComplete="username"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={credentials.password}
            onChange={(event) => setCredentials({ ...credentials, password: event.target.value })}
            autoComplete="current-password"
          />
        </label>
        <button>Unlock dashboard</button>
      </form>
    </section>
  );
}

function Overview({
  summary,
  pnlClass,
  health,
  opportunities,
  positions,
  cycles,
  focusedOpportunity,
  setSelectedOpportunityId,
  motionPaused,
  setMotionPaused,
  loading,
  lastUpdated,
}) {
  const cards = [
    ["Portfolio", currency(summary.portfolio_value), <Wallet size={20} />, "portfolio"],
    ["Total P&L", currency(summary.total_pnl), <TrendingUp size={20} />, pnlClass],
    ["Open positions", summary.open_positions ?? 0, <Activity size={20} />, "positions"],
    ["Win rate", `${number(summary.win_rate)}%`, <Brain size={20} />, "winrate"],
  ];
  const latestCycle = cycles[0];

  return (
    <div className="dashboard-grid">
      <MissionControl
        summary={summary}
        health={health}
        focusItems={opportunities}
        focusedOpportunity={focusedOpportunity}
        cycles={cycles}
        positions={positions}
        latestCycle={latestCycle}
        lastUpdated={lastUpdated}
        motionPaused={motionPaused}
        setMotionPaused={setMotionPaused}
        onSelect={setSelectedOpportunityId}
      />

      <section className="metrics">
        {cards.map(([label, value, icon, tone]) => (
          <button className={`metric ${tone}`} key={label}>
            <div className="metric-icon">{icon}</div>
            <span>{label}</span>
            <strong>{value}</strong>
          </button>
        ))}
      </section>

      <MarketTheater opportunity={focusedOpportunity} className="theater-wide" />

      <section className="panel pnl-panel">
        <PanelTitle icon={<DollarSign size={18} />} title="Realized P&L" detail={loading ? "updating" : "live"} />
        <PnlChart points={summary.pnl_curve || []} />
      </section>

      <section className="panel opportunity-deck">
        <PanelTitle icon={<Target size={18} />} title="Opportunity queue" detail={`${opportunities.length} audited`} />
        <div className="mini-feed">
          {opportunities.slice(0, 5).map((row) => (
            <button key={row.id} onClick={() => setSelectedOpportunityId(row.id)}>
              <span>{row.ticker}</span>
              <strong>{number(row.expected_return_pct)}% ER</strong>
              <Badge tone={row.signal}>{row.signal || "WATCH"}</Badge>
            </button>
          ))}
          {!opportunities.length && <p className="empty">No audited opportunities yet.</p>}
        </div>
      </section>

      <SystemHealth health={health} />
      <CycleTimeline rows={cycles} />
      <PositionConstellation rows={positions} />
    </div>
  );
}

function MissionControl({
  summary,
  health,
  focusItems,
  focusedOpportunity,
  cycles,
  positions,
  latestCycle,
  lastUpdated,
  motionPaused,
  setMotionPaused,
  onSelect,
}) {
  const cycleIntensity = Math.min(100, Math.max(8, Number(latestCycle?.markets_scanned || 0) * 8));
  const systemTone = health?.status || "unknown";

  return (
    <section className="mission-control">
      <div className="mission-copy">
        <div className="mission-kicker">
          <span>J&J AI Studio race control</span>
          <i>{summary.mode || "paper"} mode</i>
        </div>
        <h2>{summary.brand || "Kalshi predictive studio"}</h2>
        <p>{summary.slogan || "An AI studio for Main Street, not Silicon Valley."}</p>
        <div className="mission-actions">
          <button onClick={() => setMotionPaused((value) => !value)}>
            {motionPaused ? <Play size={16} /> : <Pause size={16} />}
            {motionPaused ? "Resume live motion" : "Pause motion"}
          </button>
          <button onClick={() => focusedOpportunity && onSelect(focusedOpportunity.id)}>
            <Crosshair size={16} />
            Lock focus
          </button>
        </div>
      </div>

      <div className="holo-stage" style={{ "--cycle-intensity": `${cycleIntensity}%` }}>
        <div className="stage-grid" />
        <SectorLights health={health} cycles={cycles} />
        <div className="stage-reticle">
          <SignalRadar opportunity={focusedOpportunity} health={health} />
        </div>
        <MarketMap items={focusItems} activeId={focusedOpportunity?.id} onSelect={onSelect} />
        <div className="stage-readout top-left">
          <span>health</span>
          <strong>{systemTone}</strong>
        </div>
        <div className="stage-readout top-right">
          <span>sector</span>
          <strong>{latestCycle ? `${latestCycle.markets_scanned || 0} scanned` : "pending"}</strong>
        </div>
        <div className="stage-readout bottom-left">
          <span>focus</span>
          <strong>{focusedOpportunity?.ticker || "standby"}</strong>
        </div>
        <div className="stage-readout bottom-right">
          <span>updated</span>
          <strong>{lastUpdated ? lastUpdated.toLocaleTimeString() : "waiting"}</strong>
        </div>
      </div>

      <div className="command-rail">
        <TelemetryCard icon={<Radio size={17} />} label="Pit scan" value={`${latestCycle?.markets_scanned || 0}`} detail="markets" />
        <TelemetryCard icon={<Layers3 size={17} />} label="Tyre risk" value={`${positions.length}`} detail="positions" />
        <TelemetryCard icon={<Cpu size={17} />} label="DRS signals" value={`${latestCycle?.signals_generated || 0}`} detail="last lap" />
        <TelemetryCard icon={<CommandIcon size={17} />} label="Driver focus" value={focusedOpportunity?.ticker || "none"} detail={focusedOpportunity?.type || "standby"} />
      </div>
    </section>
  );
}

function SectorLights({ health, cycles }) {
  const latest = cycles[0] || {};
  const states = [
    health?.components?.database?.status || "unknown",
    health?.components?.kalshi_api?.status || "unknown",
    health?.components?.trading_state?.status || "unknown",
    Number(latest.trades_executed || 0) > 0 ? "healthy" : "degraded",
    health?.status || "unknown",
  ];
  return (
    <div className="sector-lights" aria-label="Race control sector lights">
      {states.map((state, index) => (
        <span key={`${state}-${index}`} className={state} />
      ))}
    </div>
  );
}

function MarketMap({ items, activeId, onSelect }) {
  const displayItems = items.length
    ? items.slice(0, 9)
    : [
        { id: "standby-1", ticker: "SCAN", signal: "WATCH", confidence: 42 },
        { id: "standby-2", ticker: "RISK", signal: "NO_TRADE", confidence: 26 },
        { id: "standby-3", ticker: "CYCLE", signal: "LONG", confidence: 58 },
      ];

  return (
    <div className="market-map" aria-label="Interactive market focus map">
      {displayItems.map((item, index) => (
        <button
          key={item.id}
          className={`map-node ${activeId === item.id ? "active" : ""} ${item.signal || "neutral"}`}
          style={{
            "--x": `${18 + ((index * 31) % 64)}%`,
            "--y": `${20 + ((index * 47) % 58)}%`,
          }}
          onClick={() => onSelect(item.id)}
        >
          <span>{item.ticker}</span>
          <strong>{number(item.confidence)}%</strong>
        </button>
      ))}
    </div>
  );
}

function TelemetryCard({ icon, label, value, detail }) {
  return (
    <article className="telemetry-card">
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{detail}</em>
    </article>
  );
}

function Opportunities({ rows, focusedOpportunity, selectedOpportunityId, setSelectedOpportunityId }) {
  return (
    <div className="split-view">
      <section className="panel table-panel opportunity-feed-panel">
        <PanelTitle icon={<Brain size={18} />} title="Opportunity feed" detail={`${rows.length} audited`} />
        <div className="opportunity-list">
          {rows.map((row) => (
            <button
              className={`opportunity-card ${selectedOpportunityId === row.id ? "selected" : ""}`}
              key={row.id}
              onClick={() => setSelectedOpportunityId(row.id)}
            >
              <div className="row">
                <div>
                  <strong>{row.ticker}</strong>
                  <span>{safeDate(row.created_at)}</span>
                </div>
                <Badge tone={row.signal}>{row.signal || "WATCH"}</Badge>
              </div>
              <p>{row.reasoning || row.summary || "No rationale recorded."}</p>
              <div className="row muted">
                <span>{number(row.confidence)}% confidence</span>
                <span>{number(row.expected_return_pct)}% expected return</span>
                <span>{row.outcome_label || "open"}</span>
              </div>
            </button>
          ))}
          {!rows.length && <p className="empty">No audited opportunities yet.</p>}
        </div>
      </section>
      <MarketTheater opportunity={focusedOpportunity} className="sticky-theater" />
    </div>
  );
}

function Positions({ rows }) {
  return (
    <div className="dashboard-grid">
      <PositionConstellation rows={rows} />
      <DataTable
        title="Positions"
        rows={rows}
        fields={["ticker", "side", "quantity", "entry_price", "current_price", "unrealized_pnl", "is_open"]}
      />
    </div>
  );
}

function Cycles({ rows }) {
  return (
    <div className="dashboard-grid">
      <CycleTimeline rows={rows} large />
      <DataTable
        title="Trading cycles"
        rows={rows}
        fields={[
          "timestamp",
          "markets_scanned",
          "signals_generated",
          "trades_executed",
          "ending_balance",
          "session_pnl",
          "circuit_breaker_triggered",
        ]}
      />
    </div>
  );
}

function Costs({ costs }) {
  const cadences = costs?.cadences || [];
  const [activeIndex, setActiveIndex] = useState(0);
  const [llmRunCost, setLlmRunCost] = useState(1);
  const selected = cadences[activeIndex] || cadences[0];
  const llmEntries = Object.entries(selected?.llm_monthly || {});
  const customMonthly = selected ? selected.weekday_runs_per_month * llmRunCost : 0;

  return (
    <section className="panel table-panel cost-console">
      <PanelTitle icon={<DollarSign size={18} />} title="Railway and LLM costs" detail="weekday cadence" />
      <div className="cost-layout">
        <div className="cost-grid">
          {cadences.map((row, index) => (
            <button
              className={`cost-card ${index === activeIndex ? "active" : ""}`}
              key={row.label}
              onClick={() => setActiveIndex(index)}
            >
              <strong>{row.label}</strong>
              <span>{row.weekday_runs_per_month.toLocaleString()} runs/month</span>
              <p>{currency(row.hobby_bill_estimate)}</p>
            </button>
          ))}
          {!cadences.length && <p className="empty">Cost estimates are not available from the API yet.</p>}
        </div>
        {selected && (
          <div className="cost-stage">
            <p className="eyebrow">Selected cadence</p>
            <h2>{selected.label}</h2>
            <div className="cost-meter">
              <span>Railway estimate</span>
              <strong>{currency(selected.hobby_bill_estimate)}</strong>
            </div>
            <label className="cost-slider">
              <span>LLM cost per run</span>
              <input
                type="range"
                min="0.25"
                max="8"
                step="0.25"
                value={llmRunCost}
                onChange={(event) => setLlmRunCost(Number(event.target.value))}
              />
              <strong>{currency(llmRunCost)} / run = {currency(customMonthly)} / month</strong>
            </label>
            <div className="llm-bars">
              {llmEntries.map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <div>
                    <i style={{ width: `${Math.min(100, Number(value || 0) / 120)}%` }} />
                  </div>
                  <strong>{currency(value)}</strong>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function MarketTheater({ opportunity, className = "" }) {
  const confidence = Number(opportunity?.confidence || 0);
  const expectedReturn = Number(opportunity?.expected_return_pct || 0);
  const factors = listify(opportunity?.risk_factors || opportunity?.reasoning || opportunity?.summary);

  return (
    <section className={`panel market-theater ${className}`}>
      <PanelTitle icon={<Eye size={18} />} title="Market theater" detail={opportunity?.signal || "watch"} />
      {opportunity ? (
        <div className="theater-grid">
          <div className="cinema-frame">
            <div className="frame-overlay">
              <p className="eyebrow">{opportunity.signal || "WATCH"}</p>
              <h3>{opportunity.ticker}</h3>
              <span>{safeDate(opportunity.created_at)}</span>
            </div>
          </div>
          <div className="theater-copy">
            <div className="dial-row">
              <ProbabilityDial label="Confidence" value={confidence} />
              <ProbabilityDial label="Exp. return" value={expectedReturn} />
            </div>
            <p>{opportunity.reasoning || opportunity.summary || opportunity.market_edge || "No rationale recorded."}</p>
            <div className="factor-list">
              {factors.slice(0, 4).map((factor) => (
                <span key={factor}>{factor}</span>
              ))}
              {!factors.length && <span>No risk factors recorded</span>}
            </div>
          </div>
        </div>
      ) : (
        <p className="empty">No selected market yet.</p>
      )}
    </section>
  );
}

function SystemHealth({ health }) {
  return (
    <section className="panel health-panel">
      <PanelTitle icon={<Gauge size={18} />} title="System health" detail={health?.status || "unknown"} />
      <div className="health-list">
        {Object.entries(health?.components || {}).map(([name, component]) => (
          <div key={name}>
            <span>{name.replaceAll("_", " ")}</span>
            <strong className={component.status}>{component.status}</strong>
          </div>
        ))}
        {!Object.keys(health?.components || {}).length && <p className="empty">No health components reported.</p>}
      </div>
    </section>
  );
}

function CycleTimeline({ rows, large = false }) {
  return (
    <section className={`panel cycle-panel ${large ? "large" : ""}`}>
      <PanelTitle icon={<CalendarClock size={18} />} title="Cycle history" detail={`${rows.length} runs`} />
      <div className="cycle-track">
        {rows.slice(0, large ? 10 : 5).map((row, index) => (
          <article key={row.id || row.timestamp || index}>
            <div className="cycle-dot" />
            <div>
              <strong>{safeDate(row.timestamp)}</strong>
              <span>
                {row.markets_scanned || 0} scanned / {row.signals_generated || 0} signals /{" "}
                {row.trades_executed || 0} trades
              </span>
            </div>
            <em className={Number(row.session_pnl || 0) >= 0 ? "positive" : "negative"}>
              {currency(row.session_pnl || 0)}
            </em>
          </article>
        ))}
        {!rows.length && <p className="empty">No trading cycles logged yet.</p>}
      </div>
    </section>
  );
}

function PositionConstellation({ rows }) {
  const openRows = rows.filter((row) => row.is_open !== false).slice(0, 8);
  return (
    <section className="panel position-panel">
      <PanelTitle icon={<Zap size={18} />} title="Position constellation" detail={`${openRows.length} open`} />
      <div className="position-map">
        {openRows.map((row, index) => (
          <article
            key={row.position_id || row.id || index}
            style={{
              "--x": `${18 + ((index * 23) % 68)}%`,
              "--y": `${18 + ((index * 37) % 62)}%`,
              "--size": `${54 + Math.min(42, Number(row.quantity || 1) * 3)}px`,
            }}
            className={Number(row.unrealized_pnl || 0) >= 0 ? "positive" : "negative"}
          >
            <strong>{row.ticker || "POS"}</strong>
            <span>{currency(row.unrealized_pnl || 0)}</span>
          </article>
        ))}
        {!openRows.length && <p className="empty">No open positions.</p>}
      </div>
    </section>
  );
}

function SignalRadar({ opportunity, health }) {
  const confidence = Math.max(12, Math.min(100, Number(opportunity?.confidence || 0)));
  return (
    <div className="signal-radar" style={{ "--signal": `${confidence}%` }}>
      <div className="radar-core">
        <Sparkles size={24} />
      </div>
      <span className="ring ring-one" />
      <span className="ring ring-two" />
      <span className="ring ring-three" />
      <div className="radar-readout">
        <strong>{number(opportunity?.confidence)}%</strong>
        <span>{health?.status || "unknown"}</span>
      </div>
    </div>
  );
}

function ProbabilityDial({ label, value }) {
  const normalized = Math.max(0, Math.min(100, Number(value || 0)));
  return (
    <div className="probability-dial" style={{ "--angle": `${normalized * 3.6}deg` }}>
      <strong>{number(value)}%</strong>
      <span>{label}</span>
    </div>
  );
}

function DataTable({ title, rows, fields }) {
  return (
    <section className="panel table-panel">
      <PanelTitle icon={<Activity size={18} />} title={title} detail={`${rows.length} rows`} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {fields.map((field) => (
                <th key={field}>{field.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.id || row.position_id || index}>
                {fields.map((field) => (
                  <td key={field}>{formatCell(row[field], field)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <p className="empty">No rows yet.</p>}
      </div>
    </section>
  );
}

function PnlChart({ points }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  const plotted = useMemo(() => {
    const values = points.map((point) => Number(point.realized_pnl || 0));
    if (!values.length) return { path: "", points: [], min: 0, max: 0 };
    const min = Math.min(...values, 0);
    const max = Math.max(...values, 1);
    const coords = values.map((value, index) => {
      const x = values.length === 1 ? 50 : (index / (values.length - 1)) * 100;
      const y = 100 - ((value - min) / Math.max(max - min, 1)) * 84 - 8;
      return { x, y, value, raw: points[index] };
    });
    return {
      path: coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" "),
      points: coords,
      min,
      max,
    };
  }, [points]);

  const activePoint = plotted.points[hoverIndex ?? plotted.points.length - 1];

  function handleMove(event) {
    if (!plotted.points.length) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    setHoverIndex(Math.round(ratio * (plotted.points.length - 1)));
  }

  return (
    <div className="chart" onMouseMove={handleMove} onMouseLeave={() => setHoverIndex(null)}>
      {plotted.points.length ? (
        <>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none">
            <path className="chart-fill" d={`${plotted.path} L 100 100 L 0 100 Z`} />
            <path className="chart-line" d={plotted.path} />
            {activePoint && (
              <>
                <line className="chart-cursor" x1={activePoint.x} x2={activePoint.x} y1="0" y2="100" />
                <circle className="chart-point" cx={activePoint.x} cy={activePoint.y} r="1.6" />
              </>
            )}
          </svg>
          {activePoint && (
            <div className="chart-readout">
              <span>{safeDate(activePoint.raw?.timestamp || activePoint.raw?.created_at)}</span>
              <strong>{currency(activePoint.value)}</strong>
            </div>
          )}
        </>
      ) : (
        <span>No closed-trade P&L yet</span>
      )}
    </div>
  );
}

function TickerTape({ items, paused = false }) {
  const feed = items.length ? items : [{ label: "J&J AI Studio", value: "awaiting data", tone: "neutral" }];
  const repeated = [...feed, ...feed];
  return (
    <div className={`ticker-tape ${paused ? "paused" : ""}`} aria-label="Live market ticker">
      <div className="ticker-track">
        {repeated.map((item, index) => (
          <span key={`${item.label}-${index}`} className={item.tone}>
            <strong>{item.label}</strong>
            {item.value}
          </span>
        ))}
      </div>
    </div>
  );
}

function CommandPalette({ open, onClose, items, cycles, onSelect }) {
  const [query, setQuery] = useState("");
  const visibleItems = items
    .filter((item) => `${item.ticker} ${item.signal} ${item.type}`.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 8);

  if (!open) return null;

  return (
    <div className="command-overlay" role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="command-modal">
        <div className="command-modal-header">
          <div>
            <p className="eyebrow">Command palette</p>
            <h2>Jump to a market, position, or cycle</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close command palette">
            <X size={17} />
          </button>
        </div>
        <label className="command-search">
          <Search size={18} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} autoFocus placeholder="Search ticker, side, or signal" />
        </label>
        <div className="command-results">
          {visibleItems.map((item) => (
            <button key={item.id} onClick={() => onSelect(item)}>
              <Crosshair size={16} />
              <span>{item.ticker}</span>
              <strong>{item.signal}</strong>
              <em>{number(item.confidence)}%</em>
            </button>
          ))}
          {!visibleItems.length && <p className="empty">No matching markets or positions.</p>}
        </div>
        <div className="command-cycle-strip">
          <SlidersHorizontal size={16} />
          <span>{cycles.length} cycles logged</span>
          <strong>{cycles[0] ? `${cycles[0].markets_scanned || 0} scanned in latest run` : "No run history"}</strong>
        </div>
      </div>
    </div>
  );
}

function PanelTitle({ icon, title, detail }) {
  return (
    <div className="panel-title">
      <div>
        {icon}
        <strong>{title}</strong>
      </div>
      <span>{detail}</span>
    </div>
  );
}

function Badge({ tone, children }) {
  return <span className={`badge ${tone || "neutral"}`}>{children}</span>;
}

function currency(value) {
  return Number(value || 0).toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function number(value) {
  return Number(value || 0).toFixed(1);
}

function safeDate(value) {
  if (!value) return "not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function listify(value) {
  if (Array.isArray(value)) return value.filter(Boolean).map(String);
  if (typeof value !== "string" || !value.trim()) return [];
  return value
    .split(/\n|;|\. /)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeOpportunity(row) {
  return {
    ...row,
    id: row.id,
    type: "opportunity",
    signal: row.signal || "WATCH",
    confidence: Number(row.confidence || 0),
    expected_return_pct: Number(row.expected_return_pct || 0),
    reasoning: row.reasoning || row.summary || row.market_edge || "No rationale recorded.",
    risk_factors: row.risk_factors || [],
  };
}

function normalizePosition(row) {
  const pnl = Number(row.unrealized_pnl || 0);
  const pnlPercent = Number(row.unrealized_pnl_percent || 0);
  const confidence = Math.max(28, Math.min(92, 55 + pnlPercent * 2));
  return {
    ...row,
    id: row.position_id || row.id || row.ticker,
    type: "position",
    signal: row.side || (pnl >= 0 ? "LONG" : "SHORT"),
    confidence,
    expected_return_pct: pnlPercent,
    created_at: row.opened_at,
    reasoning: `${row.quantity || 0} contracts open. Entry ${currency(row.entry_price || 0)}, current ${currency(row.current_price || 0)}, unrealized ${currency(pnl)}.`,
    risk_factors: [
      row.is_open === false ? "Closed position" : "Open position",
      row.category ? `Category: ${row.category}` : "Category not recorded",
      pnl >= 0 ? "Positive unrealized P&L" : "Negative unrealized P&L",
    ],
  };
}

function formatCell(value, field = "") {
  if (typeof value === "number") return Math.abs(value) < 1 ? value.toFixed(3) : value.toLocaleString();
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "string" && /timestamp|date|created/i.test(field)) return safeDate(value);
  return value ?? "";
}
