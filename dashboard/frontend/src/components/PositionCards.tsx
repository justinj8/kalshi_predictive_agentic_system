import { motion } from "framer-motion";
import type { Snapshot } from "../lib/api";
import {
  fmtMoney,
  fmtPrice,
  fmtSignedPct,
  fmtTimeAgo,
} from "../lib/format";

interface Props {
  positions: Snapshot["positions"];
}

/**
 * Each open position rendered as a "car card" — race number = ticker, livery
 * stripe colored by side, big P&L delta the way sector times are displayed.
 */
export function PositionCards({ positions }: Props) {
  if (positions.length === 0) {
    return (
      <div className="hud-panel hud-corner p-6 flex items-center justify-center min-h-[160px]">
        <div className="hud-label text-f1-gray">
          NO OPEN POSITIONS — BOX RADIO QUIET
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      {positions.slice(0, 6).map((p, idx) => {
        const win = (p.unrealized_pnl ?? 0) > 0;
        const loss = (p.unrealized_pnl ?? 0) < 0;
        const side = (p.side || "").toUpperCase();
        const livery = side === "YES" ? "livery-mint" : "livery";
        const sideColor = side === "YES" ? "text-f1-mint" : "text-f1-red";

        return (
          <motion.div
            key={p.position_id}
            initial={{ y: 16, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.35, delay: idx * 0.05 }}
            className="hud-panel hud-corner overflow-hidden"
          >
            <div className="flex items-stretch">
              {/* Race number strip */}
              <div
                className={`relative ${livery} flex items-center justify-center w-14 shrink-0`}
              >
                <span className="font-display text-2xl text-ink-950 mix-blend-screen rotate-[-90deg] tracking-widest">
                  {String(idx + 1).padStart(2, "0")}
                </span>
              </div>
              <div className="flex-1 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-display text-lg tracking-wider">
                        {p.ticker}
                      </span>
                      <span
                        className={`px-1.5 py-0.5 text-[10px] font-mono rounded-sm border ${
                          side === "YES"
                            ? "border-f1-mint/40 text-f1-mint"
                            : "border-f1-red/40 text-f1-red"
                        }`}
                      >
                        {side}
                      </span>
                      <span className="px-1.5 py-0.5 text-[10px] font-mono rounded-sm bg-ink-700/60 text-f1-chalk/70">
                        ×{p.quantity}
                      </span>
                    </div>
                    {p.market_title && (
                      <div className="text-xs text-f1-chalk/60 mt-0.5 line-clamp-2">
                        {p.market_title}
                      </div>
                    )}
                  </div>
                  <div className="text-right">
                    <div
                      className={`font-display text-2xl tabular-nums leading-none ${
                        win ? "text-f1-mint" : loss ? "text-f1-red" : ""
                      }`}
                    >
                      {fmtMoney(p.unrealized_pnl)}
                    </div>
                    <div
                      className={`font-mono text-xs mt-0.5 ${
                        win ? "text-f1-mint" : loss ? "text-f1-red" : "text-f1-gray"
                      }`}
                    >
                      {fmtSignedPct(p.unrealized_pnl_percent, 2)}
                    </div>
                  </div>
                </div>

                <div className="mt-2 grid grid-cols-4 gap-2 text-[10px] font-mono">
                  <div>
                    <div className="hud-label !text-[9px]">ENTRY</div>
                    <div className={`mt-0.5 ${sideColor}`}>
                      {fmtPrice(p.entry_price)}
                    </div>
                  </div>
                  <div>
                    <div className="hud-label !text-[9px]">NOW</div>
                    <div className="mt-0.5">{fmtPrice(p.current_price)}</div>
                  </div>
                  <div>
                    <div className="hud-label !text-[9px]">STOP</div>
                    <div className="mt-0.5 text-f1-red/80">
                      {fmtPrice(p.stop_loss)}
                    </div>
                  </div>
                  <div>
                    <div className="hud-label !text-[9px]">TARGET</div>
                    <div className="mt-0.5 text-f1-mint/80">
                      {fmtPrice(p.take_profit)}
                    </div>
                  </div>
                </div>

                {/* Distance-to-target progress (visualizes how close current price
                    is to take_profit, with stop_loss as the lower bound). */}
                <DistanceBar
                  entry={p.entry_price}
                  current={p.current_price ?? p.entry_price}
                  stop={p.stop_loss}
                  target={p.take_profit}
                />

                <div className="mt-1.5 flex items-center justify-between text-[10px] font-mono text-f1-gray">
                  <span>opened {fmtTimeAgo(p.opened_at)}</span>
                  <span>{p.category || ""}</span>
                </div>
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

function DistanceBar({
  entry,
  current,
  stop,
  target,
}: {
  entry: number;
  current?: number | null;
  stop?: number | null;
  target?: number | null;
}) {
  if (!entry || !stop || !target || !current) return null;
  const lo = Math.min(stop, target, entry, current);
  const hi = Math.max(stop, target, entry, current);
  if (hi - lo < 1e-6) return null;
  const norm = (v: number) => ((v - lo) / (hi - lo)) * 100;

  return (
    <div className="mt-2 relative h-[5px] rounded-full bg-ink-700/70 overflow-hidden">
      <div
        className="absolute top-0 bottom-0 bg-f1-red/30"
        style={{ left: 0, width: `${norm(stop)}%` }}
      />
      <div
        className="absolute top-0 bottom-0 bg-f1-mint/30"
        style={{
          left: `${norm(target)}%`,
          right: 0,
        }}
      />
      <div
        className="absolute top-[-3px] h-[11px] w-[2px] bg-f1-chalk"
        style={{ left: `${norm(current)}%` }}
      />
      <div
        className="absolute top-[-2px] h-[9px] w-[1px] bg-f1-chalk/40"
        style={{ left: `${norm(entry)}%` }}
      />
    </div>
  );
}
