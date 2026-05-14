import { motion } from "framer-motion";
import type { Snapshot } from "../lib/api";
import { AnimatedNumber } from "./AnimatedNumber";
import { fmtMoney, fmtPct, fmtSignedPct } from "../lib/format";

interface Props {
  p: Snapshot["portfolio"];
}

/**
 * Driver-cluster style readouts: big balance, P&L delta, daily delta, drawdown,
 * win rate. Numbers tween between snapshots so they read as live telemetry.
 */
export function PortfolioCluster({ p }: Props) {
  const totalUp = p.total_pnl > 0;
  const totalDown = p.total_pnl < 0;
  const dailyUp = p.daily_pnl > 0;
  const dailyDown = p.daily_pnl < 0;

  return (
    <div className="hud-panel hud-corner p-4 grid grid-cols-4 gap-4">
      <Cell
        label="BALANCE"
        emphasis
        valueNode={
          <AnimatedNumber
            className="font-display text-4xl text-f1-chalk tabular-nums leading-none"
            value={p.current_balance}
            format={(v) => fmtMoney(v)}
          />
        }
        sub={`from $${p.starting_balance.toFixed(2)}`}
      />

      <Cell
        label="TOTAL P&L"
        valueNode={
          <AnimatedNumber
            className={`font-display text-3xl tabular-nums leading-none ${
              totalUp ? "text-f1-mint text-glow-mint" : totalDown ? "text-f1-red text-glow-red" : ""
            }`}
            value={p.total_pnl}
            format={(v) => fmtMoney(v)}
          />
        }
        sub={fmtSignedPct(p.total_pnl_pct, 2)}
        subClass={totalUp ? "text-f1-mint" : totalDown ? "text-f1-red" : ""}
      />

      <Cell
        label="DAILY P&L"
        valueNode={
          <AnimatedNumber
            className={`font-display text-3xl tabular-nums leading-none ${
              dailyUp ? "text-f1-mint" : dailyDown ? "text-f1-red" : ""
            }`}
            value={p.daily_pnl}
            format={(v) => fmtMoney(v)}
          />
        }
        sub={`${p.total_trades} fills · ${p.open_positions} open`}
      />

      <Cell
        label="WIN RATE"
        valueNode={
          <AnimatedNumber
            className="font-display text-3xl tabular-nums leading-none"
            value={p.win_rate}
            format={(v) => fmtPct(v, 1)}
          />
        }
        sub={
          p.sharpe_ratio != null
            ? `Sharpe ${p.sharpe_ratio.toFixed(2)}`
            : `${p.winning_trades ?? 0}W · ${p.losing_trades ?? 0}L`
        }
      />

      {/* Drawdown bar across all columns */}
      <div className="col-span-4">
        <div className="flex items-center justify-between mb-1.5">
          <span className="hud-label">CURRENT DRAWDOWN</span>
          <span className="font-mono text-[11px] text-f1-chalk/70">
            {fmtPct(p.current_drawdown, 2)} · max {fmtPct(p.max_drawdown ?? 0, 2)}
          </span>
        </div>
        <div className="relative h-2 rounded-full bg-ink-700 overflow-hidden">
          <motion.div
            className="absolute inset-y-0 left-0 bg-f1-red shadow-glow"
            initial={{ width: 0 }}
            animate={{
              width: `${Math.min(100, Math.max(0, p.current_drawdown))}%`,
            }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          />
        </div>
      </div>
    </div>
  );
}

function Cell({
  label,
  valueNode,
  sub,
  subClass,
  emphasis,
}: {
  label: string;
  valueNode: React.ReactNode;
  sub?: string;
  subClass?: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`relative ${
        emphasis ? "border-l-2 border-f1-red/60 pl-3" : ""
      }`}
    >
      <div className="hud-label">{label}</div>
      <div className="mt-1">{valueNode}</div>
      {sub && (
        <div
          className={`font-mono text-[11px] mt-1 ${subClass ?? "text-f1-gray"}`}
        >
          {sub}
        </div>
      )}
    </div>
  );
}
