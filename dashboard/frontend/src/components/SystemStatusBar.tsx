import { useEffect, useState } from "react";
import type { Snapshot } from "../lib/api";

interface Props {
  s: Snapshot["agentic_status"];
  online: boolean;
  ageMs: number;
}

/**
 * Header strip — system identity, model fleet, mode, and a UTC race clock.
 */
export function SystemStatusBar({ s, online, ageMs }: Props) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const time = now.toISOString().slice(11, 19);
  const date = now.toISOString().slice(0, 10);
  const stale = ageMs > 8000;

  return (
    <div className="flex items-stretch gap-3 px-4 py-2">
      <div className="flex items-center gap-3">
        <div className="relative h-9 w-9 bg-f1-red flex items-center justify-center font-display text-ink-950 text-lg shadow-glow">
          K
          <span className="absolute -inset-0.5 border border-f1-red animate-pulseRed pointer-events-none" />
        </div>
        <div>
          <div className="font-display text-lg leading-none tracking-wider">
            KALSHI · PIT WALL
          </div>
          <div className="hud-label">AGENTIC TRADING TELEMETRY</div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center gap-4 text-[11px] font-mono">
        <Chip label="JUDGE" value={truncModel(s.judge_model)} active />
        <Chip label="RESEARCH" value={truncModel(s.specialist_model)} />
        <Chip label="CHEAP" value={truncModel(s.cheap_model)} />
        <Divider />
        <Toggle label="WEB" on={s.enable_web_search} />
        <Toggle label="DEBATE" on={s.enable_debate} />
        <Toggle label="MEMORY" on={s.enable_memory} />
        <Toggle label="THINK" on={s.enable_extended_thinking} />
      </div>

      <div className="flex items-center gap-3">
        <div className="text-right">
          <div className="hud-label">{s.trading_mode.toUpperCase()} MODE</div>
          <div
            className={`font-mono text-[11px] tabular-nums ${
              online ? "text-f1-mint" : "text-f1-red"
            }`}
          >
            {online ? "FEED LIVE" : "FEED OFFLINE"}
            {stale && online ? " · STALE" : ""}
          </div>
        </div>
        <div className="hud-panel px-3 py-1.5">
          <div className="hud-label">UTC</div>
          <div className="font-mono text-base tabular-nums text-glow-red text-f1-red">
            {time}
          </div>
          <div className="hud-label !text-[9px] !text-f1-gray">{date}</div>
        </div>
      </div>
    </div>
  );
}

function Chip({
  label,
  value,
  active,
}: {
  label: string;
  value: string;
  active?: boolean;
}) {
  return (
    <span
      className={`flex items-center gap-1.5 px-2 py-1 rounded-sm border ${
        active
          ? "border-f1-red/70 bg-f1-red/10 text-f1-red"
          : "border-f1-chalk/15 bg-ink-900/40 text-f1-chalk/80"
      }`}
    >
      <span className="hud-label !text-[9px] !text-current opacity-80">
        {label}
      </span>
      <span className="font-mono">{value}</span>
    </span>
  );
}

function Toggle({ label, on }: { label: string; on: boolean }) {
  return (
    <span
      className={`flex items-center gap-1.5 px-2 py-1 rounded-sm border ${
        on
          ? "border-f1-mint/40 text-f1-mint bg-f1-mint/5"
          : "border-f1-chalk/15 text-f1-gray bg-ink-900/40"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${on ? "bg-f1-mint" : "bg-f1-gray"}`} />
      {label}
    </span>
  );
}

function Divider() {
  return <span className="h-4 w-px bg-f1-chalk/15" />;
}

function truncModel(m: string): string {
  if (!m) return "—";
  // Friendly shorthand: claude-opus-4-7 -> OPUS 4.7
  const op = m.match(/opus-(\d+)-(\d+)/i);
  if (op) return `OPUS ${op[1]}.${op[2]}`;
  const so = m.match(/sonnet-(\d+)-(\d+)/i);
  if (so) return `SONNET ${so[1]}.${so[2]}`;
  const ha = m.match(/haiku-(\d+)-(\d+)/i);
  if (ha) return `HAIKU ${ha[1]}.${ha[2]}`;
  return m.replace(/^claude-/, "").toUpperCase();
}
