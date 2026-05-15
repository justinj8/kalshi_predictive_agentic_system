import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { IntroCircuit } from "./IntroCircuit";
import { IntroParticles } from "./IntroParticles";
import { F1Car } from "./F1Car";
import { useIntroAsset } from "../hooks/useIntroAsset";

interface Props {
  onDone: () => void;
}

/**
 * Cinematic intro inspired by the F1-movie Silverstone opening:
 *
 *   phase 0  black + letterbox close-in
 *   phase 1  wide circuit establishing shot, Ferrari idling on the line
 *   phase 2  the Ferrari LAUNCHES — drives across frame, camera tracks &
 *            pushes in, tyre smoke + sparks + speed streaks build
 *   phase 3  speed peak → whip-blur → KALSHI · PIT WALL title slams in
 *   phase 4  telemetry vitals snap into place
 *   phase 5  grade deepens, fade to the live HUD
 *
 * If a real hero asset exists at /public/intro/hero.{mp4,webm,jpg,png} it is
 * composited as the photoreal hero layer in place of the built 2.5D circuit
 * (see useIntroAsset). Total runtime ~6s; click / Space / Esc skips.
 *
 * `onDone` is stored in a ref so the phase-timer effect can keep an EMPTY
 * dependency array — otherwise frequent parent re-renders would replace the
 * callback and cancel the pending phase timers, freezing the intro.
 */
export function IntroSequence({ onDone }: Props) {
  const [phase, setPhase] = useState<0 | 1 | 2 | 3 | 4 | 5>(0);
  const { asset } = useIntroAsset();
  const hasHero = asset.kind === "video" || asset.kind === "image";

  const onDoneRef = useRef(onDone);
  useEffect(() => {
    onDoneRef.current = onDone;
  }, [onDone]);

  // Phase timeline. Two flavours:
  //   - hero asset present  -> contemplative: let the photo/video breathe,
  //                            title comes in later, total ~8s.
  //   - built 2.5D scene    -> kinetic launch beat, total ~6s.
  // Runs once on mount.
  useEffect(() => {
    const t = hasHero
      ? { p1: 500, p2: 2600, p3: 4800, p4: 5900, p5: 7100, done: 7700 }
      : { p1: 450, p2: 1900, p3: 3400, p4: 4500, p5: 5500, done: 6100 };
    const timers = [
      setTimeout(() => setPhase(1), t.p1),
      setTimeout(() => setPhase(2), t.p2),
      setTimeout(() => setPhase(3), t.p3),
      setTimeout(() => setPhase(4), t.p4),
      setTimeout(() => setPhase(5), t.p5),
      setTimeout(() => onDoneRef.current(), t.done),
    ];
    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasHero]);

  // Click / Space / Esc / Enter skips straight to the dashboard.
  useEffect(() => {
    const skip = () => onDoneRef.current();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === " " || e.key === "Enter") skip();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Derived motion drivers.
  const launching = phase >= 2 && !hasHero;
  const drive = phase >= 3 ? 1 : phase === 2 ? 0.55 : 0;
  const intensity = hasHero ? 0 : phase >= 3 ? 1 : phase === 2 ? 0.7 : 0.06;
  const titleIn = phase >= 3;
  const vitalsIn = phase >= 4;
  const fading = phase >= 5;

  // Subtle hand-held camera shake while the car is on the move (built scene
  // only — a real photo/video already has its own camera language).
  const shake = useMemo(() => {
    if (!launching || fading) return { x: 0, y: 0 };
    return { x: [0, -3, 2, -2, 1, 0], y: [0, 2, -2, 1, -1, 0] };
  }, [launching, fading]);

  return (
    <motion.div
      className="fixed inset-0 z-[100] overflow-hidden bg-black cursor-pointer select-none"
      initial={{ opacity: 1 }}
      animate={{ opacity: fading ? 0 : 1 }}
      transition={{ duration: 0.6, ease: "easeInOut" }}
      onClick={() => onDoneRef.current()}
      onAnimationComplete={() => {
        if (fading) onDoneRef.current();
      }}
    >
      {/* ===== CAMERA RIG (everything that shakes / pushes in)
          The hero asset already animates from inside (Ken-Burns / video), so
          here we apply only a very mild push-in. The 2.5D scene gets the
          stronger launch push. ===== */}
      <motion.div
        className="absolute inset-0"
        animate={{
          scale: hasHero ? 1.04 : launching ? 1.12 : 1.02,
          x: shake.x,
          y: shake.y,
        }}
        transition={{
          scale: { duration: hasHero ? 7 : 2.4, ease: [0.16, 1, 0.3, 1] },
          x: { duration: 0.5, repeat: launching && !fading ? Infinity : 0 },
          y: { duration: 0.5, repeat: launching && !fading ? Infinity : 0 },
        }}
      >
        {/* --- HERO LAYER: real asset if present, else built circuit --- */}
        <motion.div
          className="absolute inset-0"
          initial={{ opacity: 0, scale: 1.06 }}
          animate={{ opacity: phase >= 1 ? 1 : 0, scale: 1 }}
          transition={{ duration: 1.0, ease: "easeOut" }}
        >
          {asset.kind === "video" && (
            <video
              src={asset.src}
              className="absolute inset-0 h-full w-full object-cover"
              autoPlay
              muted
              playsInline
              loop
            />
          )}
          {asset.kind === "image" && (
            // Slow cinematic Ken-Burns: push in and drift slightly right so
            // the still feels alive, not frozen. Plays for the full intro.
            <motion.img
              src={asset.src}
              className="absolute inset-0 h-full w-full object-cover"
              initial={{ scale: 1.04, x: 0 }}
              animate={{ scale: 1.18, x: "-3%" }}
              transition={{ duration: 10, ease: [0.16, 1, 0.3, 1] }}
              style={{
                // a touch of soft cinematic contrast on the still
                filter: "contrast(1.04) saturate(1.05)",
              }}
            />
          )}
          {asset.kind === "none" && <IntroCircuit drive={drive} />}
        </motion.div>

        {/* --- THE FERRARI (only on the built scene) --- */}
        {asset.kind === "none" && (
          <motion.div
            className="absolute"
            style={{ width: "46vw", bottom: "21%" }}
            initial={{ x: "-22vw", scale: 0.62, opacity: 0 }}
            animate={{
              x: launching ? "128vw" : "4vw",
              scale: launching ? 1.05 : 0.66,
              opacity: phase >= 1 ? 1 : 0,
            }}
            transition={{
              x: {
                duration: launching ? 1.9 : 0.9,
                ease: launching ? [0.42, 0, 0.78, 1] : "easeOut",
              },
              scale: { duration: launching ? 1.9 : 0.9, ease: "easeOut" },
              opacity: { duration: 0.5 },
            }}
          >
            {/* body bob/shake under load */}
            <motion.div
              animate={
                launching && !fading
                  ? { y: [0, -3, 2, -1, 0], rotate: [0, -0.6, 0.4, -0.3, 0] }
                  : { y: 0, rotate: 0 }
              }
              transition={{ duration: 0.32, repeat: launching && !fading ? Infinity : 0 }}
            >
              <F1Car intensity={intensity} className="w-full h-auto" />
            </motion.div>
            {/* motion-blur smear that grows with launch */}
            <motion.div
              className="absolute inset-0 -z-10"
              animate={{ opacity: launching ? 0.5 : 0 }}
              transition={{ duration: 0.6 }}
              style={{
                background:
                  "linear-gradient(90deg, rgba(229,16,9,0.0) 0%, rgba(20,20,24,0.55) 60%, rgba(229,16,9,0.0) 100%)",
                filter: "blur(14px)",
              }}
            />
          </motion.div>
        )}

        {/* --- PARTICLE LAYER (only meaningful on the built 2.5D scene) --- */}
        {!hasHero && (
          <IntroParticles intensity={intensity} carX={0.42} carY={0.78} />
        )}

        {/* --- SPEED BLUR on the whip transition into the title (built scene
            only — designed for the SVG launch beat) --- */}
        {!hasHero && (
          <motion.div
            className="absolute inset-0 pointer-events-none"
            initial={{ opacity: 0 }}
            animate={{ opacity: phase === 3 ? [0, 0.85, 0] : 0 }}
            transition={{ duration: 0.7, times: [0, 0.4, 1] }}
            style={{
              background:
                "repeating-linear-gradient(90deg, rgba(255,255,255,0.0) 0px, rgba(255,255,255,0.18) 2px, rgba(255,255,255,0.0) 7px)",
            }}
          />
        )}
      </motion.div>

      {/* ===== CINEMATIC GRADE =====
          Asset-aware: when a real photo/video is playing we apply only a soft
          cinematic touch (light grain + gentle vignette) so the source colour
          shows through. The built 2.5D scene gets the heavier LUT wash that
          adds depth to the vectors. */}
      <div
        className={`intro-grain absolute inset-0 pointer-events-none ${
          hasHero ? "opacity-[0.05]" : "opacity-[0.07]"
        }`}
      />
      {!hasHero && (
        <div
          className="absolute inset-0 pointer-events-none mix-blend-soft-light"
          style={{
            background:
              "radial-gradient(120% 90% at 70% 18%, rgba(255,236,200,0.28), rgba(255,236,200,0) 55%), linear-gradient(180deg, rgba(40,60,80,0.22), rgba(10,12,18,0.42))",
          }}
        />
      )}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: hasHero
            ? "radial-gradient(140% 110% at 50% 50%, rgba(0,0,0,0) 60%, rgba(0,0,0,0.42) 100%)"
            : "radial-gradient(130% 100% at 50% 46%, rgba(0,0,0,0) 52%, rgba(0,0,0,0.62) 100%)",
        }}
      />
      {/* grade deepens toward the HUD handoff (stronger on the hero path so
          the title reads cleanly over a busy photo) */}
      <motion.div
        className="absolute inset-0 pointer-events-none bg-ink-950"
        initial={{ opacity: 0 }}
        animate={{
          opacity: titleIn ? (fading ? 0.96 : hasHero ? 0.62 : 0.55) : 0,
        }}
        transition={{ duration: 0.9, ease: "easeInOut" }}
      />

      {/* ===== LETTERBOX ===== */}
      <motion.div
        className="absolute inset-x-0 top-0 bg-black z-20"
        initial={{ height: "50%" }}
        animate={{ height: fading ? "0%" : "11%" }}
        transition={{ duration: 1.0, ease: [0.83, 0, 0.17, 1] }}
      />
      <motion.div
        className="absolute inset-x-0 bottom-0 bg-black z-20"
        initial={{ height: "50%" }}
        animate={{ height: fading ? "0%" : "11%" }}
        transition={{ duration: 1.0, ease: [0.83, 0, 0.17, 1] }}
      />

      {/* ===== TITLE ===== */}
      <div className="absolute inset-0 z-30 flex flex-col items-center justify-center pointer-events-none">
        <AnimatePresence>
          {titleIn && (
            <motion.div
              key="title"
              className="flex items-center gap-3"
              initial={{ y: -10, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.4 }}
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
          initial={{ opacity: 0, x: 120, filter: "blur(22px)" }}
          animate={{
            opacity: titleIn ? 1 : 0,
            x: titleIn ? 0 : 120,
            filter: titleIn ? "blur(0px)" : "blur(22px)",
          }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        >
          <h1 className="font-display text-[clamp(48px,9vw,168px)] leading-[0.85] tracking-tight uppercase">
            <span className="text-glow-red text-f1-red">KALSHI</span>{" "}
            <span className="text-glow-mint">PIT&nbsp;WALL</span>
          </h1>
          <div className="hud-label mt-3 text-f1-chalk/75">
            AGENTIC TRADING TELEMETRY · SCUDERIA EDITION · OPUS&nbsp;4.7 /
            SONNET&nbsp;4.6 / HAIKU&nbsp;4.5
          </div>
        </motion.div>

        <AnimatePresence>
          {vitalsIn && (
            <motion.div
              key="vitals"
              className="mt-10 flex items-stretch gap-4"
              initial={{ y: 18, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
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
                  className="hud-panel px-4 py-3 min-w-[148px]"
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

      {/* ===== HUD CHROME ===== */}
      {(
        [
          ["top-[12%] left-8", "border-t-2 border-l-2"],
          ["top-[12%] right-8", "border-t-2 border-r-2"],
          ["bottom-[12%] left-8", "border-b-2 border-l-2"],
          ["bottom-[12%] right-8", "border-b-2 border-r-2"],
        ] as const
      ).map(([pos, dir], i) => (
        <motion.div
          key={pos}
          className={`absolute ${pos} h-7 w-7 ${dir} border-f1-red z-30`}
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: phase >= 1 && !fading ? 1 : 0, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.05 * i }}
        />
      ))}

      {/* shooting status, like a viewfinder */}
      <motion.div
        className="absolute top-[12%] left-1/2 -translate-x-1/2 mt-3 flex items-center gap-2 z-30"
        initial={{ opacity: 0 }}
        animate={{ opacity: phase >= 1 && !titleIn ? 1 : 0 }}
        transition={{ duration: 0.5 }}
      >
        <span className="rec-dot" />
        <span className="hud-label text-f1-red">REC · CIRCUIT FEED</span>
      </motion.div>

      {/* skip hint */}
      <motion.div
        className="absolute bottom-[12%] inset-x-0 text-center hud-label text-f1-chalk/45 z-30 mb-2"
        initial={{ opacity: 0 }}
        animate={{ opacity: phase >= 1 && !fading ? 1 : 0 }}
        transition={{ duration: 0.6, delay: 0.4 }}
      >
        CLICK · SPACE · ESC&nbsp;&nbsp;TO ENTER PIT
      </motion.div>
    </motion.div>
  );
}
