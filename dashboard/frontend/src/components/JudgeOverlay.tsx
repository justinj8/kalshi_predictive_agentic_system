import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import type { Snapshot } from "../lib/api";
import { fmtPct, fmtTimeAgo } from "../lib/format";

interface Props {
  decisions: Snapshot["decisions_recent"];
}

/**
 * The most recent judge ruling, rendered as a broadcast lower-third overlay.
 * Slides in when a new decision id appears and stays mounted thereafter.
 */
export function JudgeOverlay({ decisions }: Props) {
  const [pulseKey, setPulseKey] = useState<number>(-1);
  const top = decisions[0];

  useEffect(() => {
    if (top && top.id !== pulseKey) {
      setPulseKey(top.id);
    }
  }, [top, pulseKey]);

  if (!top || !top.judge_decision) {
    return (
      <div className="hud-panel hud-corner p-4 min-h-[200px] flex items-center justify-center">
        <div className="hud-label text-f1-gray">AWAITING JUDGE RULING</div>
      </div>
    );
  }

  const jd = top.judge_decision;
  const signal = (jd.signal || "NO_TRADE").toUpperCase();
  const signalColor =
    signal === "LONG"
      ? "text-f1-mint border-f1-mint/50 bg-f1-mint/10"
      : signal === "SHORT"
        ? "text-f1-red border-f1-red/50 bg-f1-red/10"
        : "text-f1-chalk/70 border-f1-chalk/20 bg-ink-700/40";

  const winner = (jd.debate_winner || "none").toUpperCase();
  const winnerColor =
    winner === "BULL"
      ? "text-f1-mint"
      : winner === "BEAR"
        ? "text-f1-red"
        : winner === "MIXED"
          ? "text-f1-gold"
          : "text-f1-gray";

  return (
    <div className="hud-panel hud-corner overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-f1-chalk/10 bg-ink-900/60">
        <div className="flex items-center gap-2">
          <span className="rec-dot" />
          <span className="hud-label text-f1-red">JUDGE · LIVE RULING</span>
        </div>
        <span className="text-[10px] font-mono text-f1-gray">
          {fmtTimeAgo(top.created_at)}
        </span>
      </div>

      <AnimatePresence mode="popLayout">
        <motion.div
          key={top.id}
          initial={{ opacity: 0, y: 18, filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: -12 }}
          transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
          className="p-4 space-y-3"
        >
          <div className="flex items-center gap-3">
            <span
              className={`font-display text-3xl px-3 py-1 border ${signalColor} rounded`}
            >
              {signal}
            </span>
            <div className="min-w-0 flex-1">
              <div className="font-display text-lg tracking-wider truncate">
                {top.ticker}
              </div>
              <div className="text-[11px] font-mono text-f1-gray">
                debate&nbsp;winner:{" "}
                <span className={winnerColor}>{winner}</span> · path:{" "}
                <span className="text-f1-chalk/70">
                  {top.decision_path ?? "—"}
                </span>
                {top.thinking_tokens_used != null && (
                  <>
                    {" "}
                    · thinking:{" "}
                    <span className="text-f1-chalk/70">
                      {top.thinking_tokens_used.toLocaleString()}t
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2">
            <Vital
              label="CONFIDENCE"
              value={fmtPct(jd.confidence, 0)}
              color={jd.confidence >= 70 ? "text-f1-mint" : "text-f1-chalk"}
            />
            <Vital
              label="CALIBRATED p"
              value={`${(jd.calibrated_probability * 100).toFixed(0)}%`}
            />
            <Vital
              label="EXP. RETURN"
              value={`${jd.expected_return_pct.toFixed(1)}%`}
              color={
                jd.expected_return_pct > 0 ? "text-f1-mint" : "text-f1-red"
              }
            />
            <Vital
              label="KELLY"
              value={jd.kelly_fraction.toFixed(3)}
            />
          </div>

          {jd.market_edge && (
            <div className="text-xs text-f1-chalk/85 leading-snug border-l-2 border-f1-red/70 pl-3">
              {jd.market_edge}
            </div>
          )}

          {jd.key_factors && jd.key_factors.length > 0 && (
            <div>
              <div className="hud-label">KEY FACTORS</div>
              <ul className="mt-1 space-y-0.5">
                {jd.key_factors.slice(0, 3).map((f, i) => (
                  <li
                    key={i}
                    className="text-[12px] text-f1-chalk/80 flex gap-2"
                  >
                    <span className="text-f1-mint">▸</span>
                    <span className="line-clamp-1">{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function Vital({
  label,
  value,
  color = "text-f1-chalk",
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="bg-ink-900/70 border border-f1-chalk/10 rounded-sm px-2 py-1.5">
      <div className="hud-label !text-[9px]">{label}</div>
      <div className={`font-mono text-sm tabular-nums mt-0.5 ${color}`}>
        {value}
      </div>
    </div>
  );
}
