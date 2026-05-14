import { useState } from "react";
import { IntroSequence } from "./components/IntroSequence";
import { MarketsTicker } from "./components/MarketsTicker";
import { PortfolioCluster } from "./components/PortfolioCluster";
import { PositionCards } from "./components/PositionCards";
import { ProbabilityGauge } from "./components/ProbabilityGauge";
import { JudgeOverlay } from "./components/JudgeOverlay";
import { MemoryFeed } from "./components/MemoryFeed";
import { SessionLeaderboard } from "./components/SessionLeaderboard";
import { SystemStatusBar } from "./components/SystemStatusBar";
import { TradesTape } from "./components/TradesTape";
import { useTelemetry } from "./hooks/useTelemetry";

export default function App() {
  const [introDone, setIntroDone] = useState(false);
  const { snapshot, online, ageMs } = useTelemetry(2500);

  const portfolio =
    snapshot?.portfolio ?? {
      current_balance: 0,
      starting_balance: 0,
      total_pnl: 0,
      total_pnl_pct: 0,
      daily_pnl: 0,
      open_positions: 0,
      win_rate: 0,
      total_trades: 0,
      winning_trades: 0,
      losing_trades: 0,
      peak_balance: 0,
      current_drawdown: 0,
    };

  const top = snapshot?.decisions_recent?.[0];
  const jd = top?.judge_decision;
  const gaugeProbability =
    jd?.calibrated_probability ??
    top?.calibrated_probability ??
    (portfolio.win_rate ? portfolio.win_rate / 100 : 0.5);
  const gaugeMarketImplied = jd
    ? estimateMarketImpliedFromMarketsTicker(snapshot, top?.ticker)
    : null;
  const gaugeSublabel = top?.ticker
    ? `${top.ticker} · last ruling`
    : "system idle";

  return (
    <div className="relative h-screen w-screen overflow-hidden scanlines grid-bg">
      {!introDone && <IntroSequence onDone={() => setIntroDone(true)} />}

      {/* Top header */}
      <div className="absolute inset-x-0 top-0 z-30">
        <SystemStatusBar
          s={
            snapshot?.agentic_status ?? {
              decision_path: "—",
              shadow_legacy: false,
              judge_model: "claude-opus-4-7",
              specialist_model: "claude-sonnet-4-6",
              cheap_model: "claude-haiku-4-5-20251001",
              enable_web_search: true,
              enable_debate: true,
              enable_memory: true,
              enable_extended_thinking: true,
              trading_mode: "paper",
              starting_capital: 0,
            }
          }
          online={online}
          ageMs={ageMs}
        />
        <MarketsTicker
          markets={snapshot?.markets_ticker ?? []}
          online={online}
        />
      </div>

      {/* Main grid */}
      <main className="absolute inset-0 pt-[110px] pb-[88px] px-4 grid grid-cols-12 gap-4">
        {/* Column 1: portfolio + positions + leaderboard */}
        <section className="col-span-5 flex flex-col gap-3 min-h-0">
          <PortfolioCluster p={portfolio} />
          <div className="flex-1 min-h-0 overflow-auto pr-1">
            <PositionCards positions={snapshot?.positions ?? []} />
          </div>
          <div className="h-[180px] shrink-0">
            <SessionLeaderboard sessions={snapshot?.sessions_recent ?? []} />
          </div>
        </section>

        {/* Column 2: center hero gauge + judge ruling */}
        <section className="col-span-4 flex flex-col gap-3 min-h-0">
          <div className="hud-panel hud-corner p-4 flex flex-col items-center justify-center">
            <ProbabilityGauge
              probability={gaugeProbability}
              marketImplied={gaugeMarketImplied}
              size={260}
              sublabel={gaugeSublabel}
            />
            <div className="mt-3 grid grid-cols-3 gap-2 w-full text-center">
              <Stat label="MARKETS" value={`${snapshot?.markets_ticker.length ?? 0}`} />
              <Stat
                label="DECISIONS"
                value={`${snapshot?.decisions_recent.length ?? 0}`}
              />
              <Stat
                label="LESSONS"
                value={`${snapshot?.lessons_recent.length ?? 0}`}
              />
            </div>
          </div>
          <JudgeOverlay decisions={snapshot?.decisions_recent ?? []} />
        </section>

        {/* Column 3: memory feed */}
        <section className="col-span-3 min-h-0">
          <MemoryFeed lessons={snapshot?.lessons_recent ?? []} />
        </section>
      </main>

      {/* Bottom strip: trades tape */}
      <div className="absolute inset-x-0 bottom-0 z-30 px-4 pb-3">
        <TradesTape trades={snapshot?.trades_recent ?? []} />
      </div>

      {snapshot?.standby && (
        <div className="absolute inset-x-0 bottom-[88px] z-40 flex justify-center pointer-events-none">
          <div className="hud-panel px-4 py-2 text-[11px] font-mono text-f1-gold border border-f1-gold/30 animate-flicker">
            STANDBY · {snapshot.reason ?? "trading system not yet active"}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-f1-chalk/10 rounded-sm py-1.5">
      <div className="hud-label !text-[9px]">{label}</div>
      <div className="font-mono text-base tabular-nums text-f1-chalk">
        {value}
      </div>
    </div>
  );
}

function estimateMarketImpliedFromMarketsTicker(
  snapshot: ReturnType<typeof useTelemetry>["snapshot"],
  ticker?: string,
): number | null {
  if (!snapshot || !ticker) return null;
  const m = snapshot.markets_ticker.find((m) => m.ticker === ticker);
  if (!m) return null;
  const mid = (m.yes_bid + m.yes_ask) / 2;
  if (!mid) return null;
  return Math.max(0, Math.min(1, mid));
}
