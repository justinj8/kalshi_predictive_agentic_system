import { animate, useMotionValue, useTransform, motion } from "framer-motion";
import { useEffect } from "react";

interface Props {
  value: number;
  format?: (v: number) => string;
  duration?: number;
  className?: string;
}

/**
 * Tweens the displayed number between renders. Use for any "live" metric
 * (P&L, balance, daily PnL, win rate, etc.) so it feels animated instead of
 * snapping to a new value.
 */
export function AnimatedNumber({
  value,
  format = (v) => v.toFixed(2),
  duration = 0.8,
  className,
}: Props) {
  const mv = useMotionValue(value);
  const display = useTransform(mv, (v) => format(v));

  useEffect(() => {
    const controls = animate(mv, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
    });
    return controls.stop;
  }, [value, duration, mv]);

  return <motion.span className={className}>{display}</motion.span>;
}
