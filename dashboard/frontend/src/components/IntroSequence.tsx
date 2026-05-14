import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

interface Props {
  onDone: () => void;
}

/**
 * Cinematic intro sequence inspired by the F1 movie opening: a single horizon
 * line opens into a widescreen black frame, the system identifier types in,
 * telemetry vitals snap into place, and then the HUD takes over.
 *
 * Total runtime ~4.2s. Calls onDone() at the end.
 */
export function IntroSequence({ onDone }: Props) {
  const [phase, setPhase] = useState<0 | 1 | 2 | 3 | 4>(0);

  useEffect(() => {
    const t1 = setTimeout(() => setPhase(1), 350);
    const t2 = setTimeout(() => setPhase(2), 1300);
    const t3 = setTimeout(() => setPhase(3), 2300);
    const t4 = setTimeout(() => setPhase(4), 3500);
    const t5 = setTimeout(() => onDone(), 4200);
    return () => [t1, t2, t3, t4, t5].forEach(clearTimeout);
  }, [onDone]);

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-ink-950 overflow-hidden"
      initial={{ opacity: 1 }}
      animate={{ opacity: phase >= 4 ? 0 : 1 }}
      transition={{ duration: 0.6, ease: "easeInOut" }}
      onAnimationComplete={() => {
        if (phase >= 4) onDone();
      }}
    >
      {/* Letterbox bars */}
      <motion.div
        className="absolute inset-x-0 top-0 bg-black"
        initial={{ height: "50%" }}
        animate={{ height: phase >= 4 ? "0%" : "12%" }}
        transition={{ duration: 1.0, ease: [0.83, 0, 0.17, 1] }}
      />
      <motion.div
        className="absolute inset-x-0 bottom-0 bg-black"
        initial={{ height: "50%" }}
        animate={{ height: phase >= 4 ? "0%" : "12%" }}
        transition={{ duration: 1.0, ease: [0.83, 0, 0.17, 1] }}
      />

      {/* Red horizon line */}
      <motion.div
        className="absolute left-0 right-0 mx-auto h-[2px] bg-f1-red shadow-[0_0_30px_0_rgba(225,6,0,0.9)]"
        style={{ top: "50%" }}
        initial={{ width: "0%", opacity: 0 }}
        animate={{
          width: phase >= 1 ? (phase >= 3 ? "100%" : "70%") : "0%",
          opacity: phase >= 1 ? 1 : 0,
        }}
        transition={{ duration: 0.9, ease: "easeOut" }}
      />

      {/* Speedlines flying past */}
      {phase >= 2 && (
        <div className="speedlines absolute inset-y-1/2 left-0 right-0 h-24">
          {[...Array(7)].map((_, i) => (
            <span
              key={i}
              style={{
                top: `${i * 4 - 8}px`,
                animationDelay: `${i * 0.18}s`,
              }}
            />
          ))}
        </div>
      )}

      {/* Center identifier */}
      <div className="relative z-10 flex flex-col items-center gap-3">
        <AnimatePresence>
          {phase >= 2 && (
            <motion.div
              key="badge"
              className="flex items-center gap-3"
              initial={{ y: -12, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4, ease: "easeOut" }}
            >
              <span className="rec-dot" />
              <span className="hud-label tracking-[0.5em] text-f1-red">
                LIVE FEED
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.div
          className="text-center"
          initial={{ opacity: 0, scale: 0.94, filter: "blur(8px)" }}
          animate={{
            opacity: phase >= 2 ? 1 : 0,
            scale: phase >= 2 ? 1 : 0.94,
            filter: phase >= 2 ? "blur(0px)" : "blur(8px)",
          }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        >
          <h1 className="font-display text-[clamp(48px,9vw,168px)] leading-[0.85] tracking-tight text-f1-chalk uppercase">
            <span className="text-glow-red text-f1-red">KALSHI</span>{" "}
            <span className="text-glow-mint">PIT&nbsp;WALL</span>
          </h1>
          <div className="hud-label mt-3 text-f1-chalk/70">
            AGENTIC TRADING TELEMETRY · V1.0 · OPUS&nbsp;4.7 / SONNET&nbsp;4.6 /
            HAIKU&nbsp;4.5
          </div>
        </motion.div>

        {/* Vitals strip */}
        <AnimatePresence>
          {phase >= 3 && (
            <motion.div
              key="vitals"
              className="mt-10 flex items-stretch gap-5"
              initial={{ y: 18, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.45 }}
            >
              {[
                ["JUDGE", "OPUS 4.7"],
                ["RESEARCH", "SONNET 4.6"],
                ["DEBATE", "BULL/BEAR/RED"],
                ["MEMORY", "MiniLM-L6"],
                ["MODE", "PAPER"],
              ].map(([label, value], i) => (
                <motion.div
                  key={label}
                  className="hud-panel px-4 py-3 min-w-[150px]"
                  initial={{ y: 12, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ duration: 0.4, delay: i * 0.08 }}
                >
                  <div className="hud-label">{label}</div>
                  <div className="font-mono text-sm text-f1-chalk mt-1">
                    {value}
                  </div>
                </motion.div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Corner brackets */}
      {(
        [
          ["top-8 left-8", "border-t-2 border-l-2"],
          ["top-8 right-8", "border-t-2 border-r-2"],
          ["bottom-8 left-8", "border-b-2 border-l-2"],
          ["bottom-8 right-8", "border-b-2 border-r-2"],
        ] as const
      ).map(([pos, dir], i) => (
        <motion.div
          key={pos}
          className={`absolute ${pos} h-7 w-7 ${dir} border-f1-red`}
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{
            opacity: phase >= 1 ? 1 : 0,
            scale: phase >= 1 ? 1 : 0.5,
          }}
          transition={{ duration: 0.5, delay: 0.05 * i, ease: "easeOut" }}
        />
      ))}
    </motion.div>
  );
}
