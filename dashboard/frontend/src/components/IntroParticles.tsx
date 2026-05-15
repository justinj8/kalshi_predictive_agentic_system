import { useEffect, useRef } from "react";

interface Props {
  /** 0 = calm establishing shot, 1 = full launch / speed peak. */
  intensity: number;
  /** Where the car's rear contact patch is, in 0..1 screen coords. */
  carX: number;
  carY: number;
}

interface P {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  max: number;
  size: number;
  kind: "smoke" | "spark" | "streak";
}

/**
 * Canvas particle layer for the intro: tyre smoke + grit kicked up behind the
 * Ferrari, occasional sparks off the floor, and horizontal speed streaks that
 * intensify with `intensity`. Pure canvas so it stays cheap at 60fps.
 */
export function IntroParticles({ intensity, carX, carY }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef({ intensity, carX, carY });
  stateRef.current = { intensity, carX, carY };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx: CanvasRenderingContext2D | null = canvas.getContext("2d");
    if (!ctx) return;
    // Stable non-null binding so the nested render closure keeps narrowing.
    const g2d: CanvasRenderingContext2D = ctx;

    let raf = 0;
    let particles: P[] = [];
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    function resize() {
      const c = canvasRef.current!;
      c.width = c.clientWidth * dpr;
      c.height = c.clientHeight * dpr;
    }
    resize();
    window.addEventListener("resize", resize);

    function spawn(w: number, h: number) {
      const { intensity: it, carX: cx, carY: cy } = stateRef.current;
      const px = cx * w;
      const py = cy * h;

      // Tyre smoke + grit: more, faster, behind the car as intensity rises.
      const smokeCount = Math.round(it * 4);
      for (let i = 0; i < smokeCount; i++) {
        particles.push({
          x: px + (Math.random() - 0.5) * 30 * dpr,
          y: py + (Math.random() - 0.2) * 20 * dpr,
          vx: -(1.5 + Math.random() * 5) * (0.4 + it) * dpr,
          vy: -(Math.random() * 1.6 + 0.2) * dpr,
          life: 0,
          max: 50 + Math.random() * 60,
          size: (8 + Math.random() * 26) * dpr,
          kind: "smoke",
        });
      }
      // Sparks: rare, only at high intensity.
      if (it > 0.55 && Math.random() < it * 0.5) {
        particles.push({
          x: px + (Math.random() - 0.5) * 20 * dpr,
          y: py + 6 * dpr,
          vx: -(6 + Math.random() * 10) * dpr,
          vy: (Math.random() - 0.6) * 4 * dpr,
          life: 0,
          max: 14 + Math.random() * 14,
          size: (1.4 + Math.random() * 1.8) * dpr,
          kind: "spark",
        });
      }
      // Speed streaks across the whole frame.
      const streakCount = Math.round(it * 3);
      for (let i = 0; i < streakCount; i++) {
        particles.push({
          x: w + Math.random() * 200 * dpr,
          y: Math.random() * h,
          vx: -(20 + Math.random() * 40) * (0.5 + it) * dpr,
          vy: 0,
          life: 0,
          max: 20 + Math.random() * 20,
          size: (40 + Math.random() * 160) * dpr,
          kind: "streak",
        });
      }
    }

    function frame() {
      const c = canvasRef.current;
      if (!c) return;
      const w = c.width;
      const h = c.height;
      g2d.clearRect(0, 0, w, h);

      spawn(w, h);

      particles = particles.filter((p) => p.life < p.max);
      for (const p of particles) {
        p.life++;
        p.x += p.vx;
        p.y += p.vy;
        const t = p.life / p.max;

        if (p.kind === "smoke") {
          p.vx *= 0.97;
          p.vy -= 0.04 * dpr; // drifts up
          const grow = p.size * (0.6 + t * 1.6);
          const alpha = (1 - t) * 0.34;
          const g = g2d.createRadialGradient(p.x, p.y, 0, p.x, p.y, grow);
          g.addColorStop(0, `rgba(218,216,210,${alpha})`);
          g.addColorStop(1, "rgba(190,188,182,0)");
          g2d.fillStyle = g;
          g2d.beginPath();
          g2d.arc(p.x, p.y, grow, 0, Math.PI * 2);
          g2d.fill();
        } else if (p.kind === "spark") {
          p.vy += 0.35 * dpr; // gravity
          g2d.strokeStyle = `rgba(255,${170 + Math.random() * 60 | 0},80,${1 - t})`;
          g2d.lineWidth = p.size;
          g2d.beginPath();
          g2d.moveTo(p.x, p.y);
          g2d.lineTo(p.x - p.vx * 1.4, p.y - p.vy * 1.4);
          g2d.stroke();
        } else {
          // streak
          g2d.strokeStyle = `rgba(236,238,240,${(1 - t) * 0.22})`;
          g2d.lineWidth = 1.4 * dpr;
          g2d.beginPath();
          g2d.moveTo(p.x, p.y);
          g2d.lineTo(p.x + p.size, p.y);
          g2d.stroke();
        }
      }

      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 h-full w-full pointer-events-none"
    />
  );
}
