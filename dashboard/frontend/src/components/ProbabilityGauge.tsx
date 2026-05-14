import { animate, useMotionValue, useMotionValueEvent } from "framer-motion";
import { useEffect, useState } from "react";

interface Props {
  /** 0-1 calibrated probability. */
  probability: number;
  /** 0-1 market-implied probability (rendered as a thin tick). */
  marketImplied?: number | null;
  /** 0-1 size of the gauge in viewport units (default 220px). */
  size?: number;
  label?: string;
  sublabel?: string;
}

/**
 * RPM-style arc gauge. The fill arc colors shift from blue -> mint -> gold ->
 * red as probability moves from 0 toward 1. A thin tick marks the market's
 * implied probability so the "edge" is visually obvious.
 */
export function ProbabilityGauge({
  probability,
  marketImplied,
  size = 220,
  label = "CALIBRATED p(YES)",
  sublabel,
}: Props) {
  const mv = useMotionValue(0);
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const c = animate(mv, Math.max(0, Math.min(1, probability)), {
      duration: 1.0,
      ease: [0.16, 1, 0.3, 1],
    });
    return c.stop;
  }, [probability, mv]);

  useMotionValueEvent(mv, "change", (v) => setDisplay(v));

  const radius = size / 2 - 12;
  const cx = size / 2;
  const cy = size / 2 + 8; // shift so the open bottom feels balanced
  const startAngle = 135;
  const endAngle = 405; // 270° sweep
  const total = endAngle - startAngle;

  function polar(angleDeg: number, r = radius) {
    const a = (angleDeg * Math.PI) / 180;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)] as const;
  }

  function arcPath(start: number, end: number, r: number) {
    const [sx, sy] = polar(start, r);
    const [ex, ey] = polar(end, r);
    const large = end - start > 180 ? 1 : 0;
    return `M ${sx} ${sy} A ${r} ${r} 0 ${large} 1 ${ex} ${ey}`;
  }

  const fillEnd = startAngle + total * display;
  const color =
    display >= 0.72
      ? "#E10600"
      : display >= 0.58
        ? "#FFD200"
        : display >= 0.42
          ? "#00D2BE"
          : "#5b8fb0";

  return (
    <div className="flex flex-col items-center" style={{ width: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="overflow-visible"
      >
        <defs>
          <radialGradient id="rg-bg" cx="50%" cy="55%" r="55%">
            <stop offset="0%" stopColor="rgba(225,6,0,0.06)" />
            <stop offset="100%" stopColor="rgba(225,6,0,0)" />
          </radialGradient>
          <filter id="rg-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background disc */}
        <circle cx={cx} cy={cy} r={radius + 6} fill="url(#rg-bg)" />

        {/* Tick marks every 10% */}
        {Array.from({ length: 21 }, (_, i) => i / 20).map((t, i) => {
          const a = startAngle + total * t;
          const [x1, y1] = polar(a, radius - 3);
          const [x2, y2] = polar(a, radius - (i % 5 === 0 ? 16 : 9));
          return (
            <line
              key={t}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={i % 5 === 0 ? "rgba(244,244,240,0.6)" : "rgba(244,244,240,0.18)"}
              strokeWidth={i % 5 === 0 ? 1.5 : 1}
            />
          );
        })}

        {/* Base ring */}
        <path
          d={arcPath(startAngle, endAngle, radius)}
          fill="none"
          stroke="rgba(244,244,240,0.06)"
          strokeWidth={8}
          strokeLinecap="round"
        />

        {/* Animated fill */}
        <path
          d={arcPath(startAngle, fillEnd, radius)}
          fill="none"
          stroke={color}
          strokeWidth={8}
          strokeLinecap="round"
          filter="url(#rg-glow)"
          style={{ transition: "stroke 0.4s ease" }}
        />

        {/* Market-implied tick */}
        {marketImplied != null && (
          (() => {
            const a = startAngle + total * Math.max(0, Math.min(1, marketImplied));
            const [x1, y1] = polar(a, radius - 18);
            const [x2, y2] = polar(a, radius + 8);
            return (
              <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke="#F4F4F0"
                strokeWidth={2}
                strokeLinecap="round"
                opacity={0.85}
              />
            );
          })()
        )}

        {/* Hub */}
        <circle cx={cx} cy={cy} r={4} fill="#E10600" />
      </svg>

      <div className="-mt-12 text-center">
        <div
          className="font-display text-5xl tabular-nums leading-none"
          style={{ color }}
        >
          {Math.round(display * 100)}
          <span className="text-2xl opacity-70 ml-0.5">%</span>
        </div>
        <div className="hud-label mt-1">{label}</div>
        {sublabel && (
          <div className="text-xs font-mono text-f1-gray mt-0.5">{sublabel}</div>
        )}
      </div>
    </div>
  );
}
