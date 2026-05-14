import { AnimatePresence, motion } from "framer-motion";
import type { Snapshot } from "../lib/api";
import { fmtMoney, fmtTimeAgo } from "../lib/format";

interface Props {
  lessons: Snapshot["lessons_recent"];
}

const TYPE_COLORS: Record<string, string> = {
  win_pattern: "text-f1-mint border-f1-mint/40",
  loss_pattern: "text-f1-red border-f1-red/40",
  calibration: "text-f1-gold border-f1-gold/40",
  data_quality: "text-f1-chalk/80 border-f1-chalk/30",
  edge_decay: "text-f1-gray border-f1-gray/40",
};

/**
 * Memory recall stream — styled like pit-wall radio chatter. New lessons
 * fade in from the top and older ones recede.
 */
export function MemoryFeed({ lessons }: Props) {
  return (
    <div className="hud-panel hud-corner h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-f1-chalk/10 bg-ink-900/60">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-f1-mint animate-pulseRed" />
          <span className="hud-label text-f1-mint">MEMORY · PIT RADIO</span>
        </div>
        <span className="text-[10px] font-mono text-f1-gray">
          {lessons.length} lessons
        </span>
      </div>

      <div className="flex-1 overflow-auto p-3 space-y-2">
        {lessons.length === 0 && (
          <div className="hud-label text-f1-gray text-center py-8">
            BOX RADIO QUIET — NO LESSONS YET
          </div>
        )}
        <AnimatePresence initial={false}>
          {lessons.slice(0, 8).map((l) => (
            <motion.div
              key={l.id}
              layout
              initial={{ opacity: 0, x: -16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 16 }}
              transition={{ duration: 0.35 }}
              className="text-[12px] leading-snug bg-ink-900/40 rounded-sm border border-f1-chalk/5 p-2"
            >
              <div className="flex items-center justify-between gap-2 text-[10px] font-mono mb-1">
                <span
                  className={`px-1.5 py-0.5 rounded-sm border ${
                    TYPE_COLORS[l.lesson_type] || "text-f1-chalk/70 border-f1-chalk/20"
                  }`}
                >
                  {l.lesson_type.toUpperCase().replace("_", " ")}
                </span>
                <span className="text-f1-gray">
                  {l.ticker || "—"} · {fmtTimeAgo(l.created_at)}
                  {l.outcome_pnl != null && (
                    <>
                      {" "}
                      ·{" "}
                      <span
                        className={
                          l.outcome_pnl > 0
                            ? "text-f1-mint"
                            : l.outcome_pnl < 0
                              ? "text-f1-red"
                              : "text-f1-gray"
                        }
                      >
                        {fmtMoney(l.outcome_pnl)}
                      </span>
                    </>
                  )}
                </span>
              </div>
              <div className="text-f1-chalk/85 line-clamp-3">{l.text}</div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
