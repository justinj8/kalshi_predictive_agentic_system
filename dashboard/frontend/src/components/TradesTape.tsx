import { AnimatePresence, motion } from "framer-motion";
import type { Snapshot } from "../lib/api";
import { fmtMoney, fmtPrice, fmtSignedPct, fmtTimeAgo } from "../lib/format";

interface Props {
  trades: Snapshot["trades_recent"];
}

/**
 * Bottom-strip trades tape — broadcast-style with newest trade pinned left and
 * fade-out on the right. Each entry pulses on insert.
 */
export function TradesTape({ trades }: Props) {
  return (
    <div className="hud-panel hud-corner flex items-stretch h-16 overflow-hidden">
      <div className="px-4 py-2 flex flex-col justify-between bg-ink-900/80 border-r border-f1-chalk/10 min-w-[150px]">
        <span className="hud-label">TRADE&nbsp;TAPE</span>
        <span className="font-mono text-[10px] text-f1-gray">
          last&nbsp;{trades.length}
        </span>
      </div>

      <div
        className="flex-1 relative overflow-hidden"
        style={{
          maskImage:
            "linear-gradient(90deg, #000 0, #000 88%, transparent 100%)",
        }}
      >
        <div className="absolute inset-0 flex items-center gap-3 px-4">
          <AnimatePresence initial={false}>
            {trades.length === 0 && (
              <motion.div
                key="empty"
                className="hud-label text-f1-gray"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                NO FILLS YET — STANDBY
              </motion.div>
            )}
            {trades.slice(0, 14).map((t, idx) => {
              const win = (t.realized_pnl ?? 0) > 0;
              const loss = (t.realized_pnl ?? 0) < 0;
              const side = (t.side || "").toUpperCase();
              const sideColor =
                side === "YES" ? "text-f1-mint" : "text-f1-red";
              return (
                <motion.div
                  key={`${t.timestamp}-${t.ticker}-${idx}`}
                  layout
                  initial={{ x: -32, opacity: 0, scale: 0.96 }}
                  animate={{ x: 0, opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.4, ease: "easeOut" }}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-sm border ${
                    idx === 0
                      ? "border-f1-red/60 bg-f1-red/10 shadow-glow"
                      : "border-f1-chalk/10 bg-ink-900/40"
                  }`}
                >
                  <span className="hud-label text-f1-chalk/50">
                    {fmtTimeAgo(t.timestamp)}
                  </span>
                  <span className="font-display tracking-wider text-sm">
                    {t.ticker}
                  </span>
                  <span className={`text-xs font-mono ${sideColor}`}>
                    {side}
                  </span>
                  <span className="text-xs font-mono text-f1-chalk/80">
                    {t.quantity}@{fmtPrice(t.price)}
                  </span>
                  {t.realized_pnl != null && (
                    <span
                      className={`text-xs font-mono px-1.5 py-0.5 rounded-sm ${
                        win
                          ? "bg-f1-mint/15 text-f1-mint"
                          : loss
                            ? "bg-f1-red/15 text-f1-red"
                            : "bg-f1-chalk/10 text-f1-chalk/70"
                      }`}
                    >
                      {fmtMoney(t.realized_pnl)}
                      {t.pnl_percent != null
                        ? ` · ${fmtSignedPct(t.pnl_percent, 1)}`
                        : ""}
                    </span>
                  )}
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
