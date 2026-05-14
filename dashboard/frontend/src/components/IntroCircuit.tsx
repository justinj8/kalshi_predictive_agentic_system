import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { useEffect } from "react";

interface Props {
  /** 0 = wide establishing shot, 1 = pushed-in / speed peak. */
  drive: number;
}

/**
 * A wide, naturalistic circuit establishing shot — modelled on the F1-movie
 * Silverstone reference: overcast sky, distant treeline, two grandstands, a
 * modern pit building, grey asphalt with a gentle curve, black-and-white
 * kerbs, grass verges.
 *
 * Everything is layered for parallax: as `drive` goes 0 -> 1 the camera
 * eases in, layers separate at different rates, and the track surface streaks.
 * The Ferrari itself is composited on top by IntroSequence so it can run its
 * own launch animation independent of the environment.
 *
 * viewBox 0 0 1920 1080.
 */
export function IntroCircuit({ drive }: Props) {
  // Smooth the incoming drive value so camera motion is never janky.
  const d = useMotionValue(0);
  useEffect(() => {
    const c = animate(d, drive, { duration: 1.1, ease: [0.16, 1, 0.3, 1] });
    return c.stop;
  }, [drive, d]);

  // Parallax: far layers barely move, near layers move a lot.
  const skyY = useTransform(d, [0, 1], [0, -14]);
  const standsX = useTransform(d, [0, 1], [0, -70]);
  const standsScale = useTransform(d, [0, 1], [1, 1.06]);
  const treeX = useTransform(d, [0, 1], [0, -46]);
  const trackScale = useTransform(d, [0, 1], [1, 1.14]);
  const trackY = useTransform(d, [0, 1], [0, 40]);
  const kerbX = useTransform(d, [0, 1], [0, -420]);
  const grassX = useTransform(d, [0, 1], [0, -260]);
  const streak = useTransform(d, [0, 0.4, 1], [0, 0.15, 0.9]);

  return (
    <div className="absolute inset-0 overflow-hidden bg-[#d6d9dc]">
      <svg
        viewBox="0 0 1920 1080"
        preserveAspectRatio="xMidYMid slice"
        className="absolute inset-0 h-full w-full"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          {/* Overcast sky — soft, high-key, faintly cool */}
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#bfc6cc" />
            <stop offset="55%" stopColor="#d6dadd" />
            <stop offset="100%" stopColor="#e9ebec" />
          </linearGradient>
          {/* Asphalt */}
          <linearGradient id="asphalt" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#9a9ea3" />
            <stop offset="45%" stopColor="#7e8288" />
            <stop offset="100%" stopColor="#5c5f64" />
          </linearGradient>
          {/* Grass */}
          <linearGradient id="grass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5e7d3e" />
            <stop offset="100%" stopColor="#3d5526" />
          </linearGradient>
          <linearGradient id="grassNear" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4f6c34" />
            <stop offset="100%" stopColor="#2c3d1c" />
          </linearGradient>
          {/* Grandstand roof */}
          <linearGradient id="roof" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e7e9ea" />
            <stop offset="100%" stopColor="#aab0b4" />
          </linearGradient>
          <filter id="haze" x="-10%" y="-10%" width="120%" height="120%">
            <feGaussianBlur stdDeviation="3" />
          </filter>
          <filter id="treeBlur" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="6" />
          </filter>
        </defs>

        {/* ---- SKY ---- */}
        <motion.g style={{ y: skyY }}>
          <rect x="-40" y="-40" width="2000" height="560" fill="url(#sky)" />
          {/* soft cloud banding */}
          <ellipse cx="520" cy="150" rx="520" ry="70" fill="#ffffff" opacity="0.35" />
          <ellipse cx="1400" cy="110" rx="600" ry="80" fill="#ffffff" opacity="0.3" />
          <ellipse cx="980" cy="230" rx="700" ry="60" fill="#c4cace" opacity="0.4" />
        </motion.g>

        {/* ---- DISTANT TREELINE ---- */}
        <motion.g style={{ x: treeX }} filter="url(#treeBlur)">
          <path
            d="M-40 470 Q 140 412 320 452 Q 520 400 760 446 Q 1000 402 1240 450
               Q 1500 404 1720 452 Q 1860 430 1980 460 L1980 520 L-40 520 Z"
            fill="#5a6f4a"
            opacity="0.85"
          />
          {/* a couple of feature trees, like the lone tree in the reference */}
          <ellipse cx="1500" cy="420" rx="70" ry="78" fill="#46583b" />
          <ellipse cx="250" cy="436" rx="58" ry="60" fill="#46583b" />
        </motion.g>

        {/* ---- GRANDSTANDS + PIT BUILDING ---- */}
        <motion.g style={{ x: standsX, scale: standsScale, originX: "960px", originY: "460px" }}>
          {/* left grandstand */}
          <g>
            <rect x="40" y="392" width="560" height="118" fill="#3f4a57" />
            {/* seating speckle */}
            {Array.from({ length: 7 }).map((_, r) => (
              <rect
                key={r}
                x="52"
                y={400 + r * 15}
                width="536"
                height="6"
                fill={r % 2 ? "#52617240" : "#6a7a8c40"}
              />
            ))}
            {/* angular roof */}
            <path d="M20 392 L300 320 L620 360 L600 396 L40 396 Z" fill="url(#roof)" />
            <path d="M20 392 L300 320 L620 360" fill="none" stroke="#8c9298" strokeWidth="2" />
          </g>

          {/* pit building (modern, dark glass band) */}
          <g>
            <rect x="760" y="356" width="430" height="150" fill="#cdd1d4" />
            <rect x="760" y="386" width="430" height="44" fill="#23282e" />
            <rect x="760" y="356" width="430" height="10" fill="#9aa0a5" />
            {/* control tower */}
            <rect x="1090" y="300" width="96" height="60" fill="#1d2228" />
            <rect x="1098" y="312" width="80" height="20" fill="#3d4650" />
          </g>

          {/* right grandstand */}
          <g>
            <rect x="1320" y="404" width="540" height="104" fill="#3f4a57" />
            {Array.from({ length: 6 }).map((_, r) => (
              <rect
                key={r}
                x="1332"
                y={412 + r * 15}
                width="516"
                height="6"
                fill={r % 2 ? "#52617240" : "#6a7a8c40"}
              />
            ))}
            <path d="M1300 404 L1560 350 L1880 392 L1860 408 L1320 408 Z" fill="url(#roof)" />
          </g>

          {/* catch fencing hint */}
          <rect x="40" y="486" width="1840" height="3" fill="#9298a0" opacity="0.5" />
        </motion.g>

        {/* ---- FAR GRASS BAND ---- */}
        <rect x="-40" y="500" width="2000" height="70" fill="url(#grass)" />

        {/* ---- TRACK SURFACE (gentle curve, perspective) ---- */}
        <motion.g style={{ scale: trackScale, y: trackY, originX: "960px", originY: "1080px" }}>
          {/* asphalt ribbon */}
          <path
            d="M-40 560 L1980 560 L1980 690 Q 1300 700 960 760 Q 600 820 -40 980 Z"
            fill="url(#asphalt)"
          />
          <path
            d="M-40 980 L960 760 Q 1300 700 1980 690 L1980 1120 L-40 1120 Z"
            fill="url(#asphalt)"
          />
          {/* worn racing line */}
          <path
            d="M-40 940 Q 560 800 960 740 Q 1320 690 1980 660"
            fill="none"
            stroke="#54585d"
            strokeWidth="46"
            opacity="0.55"
            filter="url(#haze)"
          />
          {/* white track edge line (far) */}
          <path
            d="M-40 566 L1980 566"
            stroke="#e8e9ea"
            strokeWidth="4"
            opacity="0.85"
          />
          {/* speed streak overlay on the asphalt */}
          <motion.g style={{ opacity: streak }}>
            {Array.from({ length: 14 }).map((_, i) => (
              <rect
                key={i}
                x={-40 + i * 150}
                y={640 + (i % 3) * 70}
                width="120"
                height="3"
                fill="#c9ccce"
                opacity="0.5"
              />
            ))}
          </motion.g>
        </motion.g>

        {/* ---- KERB (black/white, foreground-left, hugging the track edge) ---- */}
        {/* A short curved strip tucked into the bottom-left corner — a framing
            element, like the F1-movie reference, NOT a beam across the frame. */}
        <motion.g style={{ x: kerbX }}>
          <g>
            {/* the kerb follows the lower-left track boundary */}
            {Array.from({ length: 13 }).map((_, i) => {
              // step along a gentle curve from the corner up toward mid-left
              const fx = i / 12;
              const x = -40 + fx * 560;
              const y = 1010 - fx * fx * 360; // curves upward
              const ang = -34 + fx * 20; // eases flatter as it recedes
              const w = 58 - fx * 18; // narrows with distance
              const h = 30 - fx * 10;
              return (
                <rect
                  key={i}
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  fill={i % 2 ? "#eceded" : "#c4302b"}
                  transform={`rotate(${ang} ${x + w / 2} ${y + h / 2})`}
                />
              );
            })}
          </g>
        </motion.g>

        {/* ---- FOREGROUND GRASS VERGE (bottom-left, inside the kerb) ---- */}
        <motion.g style={{ x: grassX }}>
          <path
            d="M-260 1180 L-260 980 Q 0 980 260 1080 Q 360 1130 420 1180 Z"
            fill="url(#grassNear)"
          />
          {/* near-side grass speckle for texture */}
          <path
            d="M-200 1060 Q 0 1010 200 1080"
            fill="none"
            stroke="#3a4f24"
            strokeWidth="10"
            opacity="0.5"
          />
        </motion.g>
      </svg>

      {/* foreground depth-of-field blur on the very bottom edge */}
      <div
        className="absolute inset-x-0 bottom-0 h-[14%] pointer-events-none"
        style={{
          backdropFilter: "blur(2px)",
          WebkitMaskImage:
            "linear-gradient(180deg, transparent, #000 70%)",
          maskImage: "linear-gradient(180deg, transparent, #000 70%)",
        }}
      />

      {/* ---- ATMOSPHERIC DEPTH ---- */}
      {/* distance haze fading the far layers */}
      <div
        className="absolute inset-x-0 top-0 h-[52%] pointer-events-none"
        style={{
          background:
            "linear-gradient(180deg, rgba(214,217,220,0.0) 30%, rgba(214,217,220,0.55) 100%)",
        }}
      />
    </div>
  );
}
