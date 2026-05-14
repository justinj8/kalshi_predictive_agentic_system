import type { Snapshot } from "../lib/api";
import { fmtMoney, fmtTimeAgo } from "../lib/format";

interface Props {
  sessions: Snapshot["sessions_recent"];
}

/**
 * Recent trading cycles, race-position style. The most profitable session is
 * P1 and so on. Each row shows scanned / signals / trades / pnl.
 */
export function SessionLeaderboard({ sessions }: Props) {
  const ranked = [...sessions]
    .sort((a, b) => (b.session_pnl ?? 0) - (a.session_pnl ?? 0))
    .slice(0, 8);

  return (
    <div className="hud-panel hud-corner h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-f1-chalk/10 bg-ink-900/60">
        <span className="hud-label text-f1-chalk">SESSION LEADERBOARD</span>
        <span className="text-[10px] font-mono text-f1-gray">
          last&nbsp;{sessions.length} cycles
        </span>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full text-[11px] font-mono">
          <thead className="text-f1-gray border-b border-f1-chalk/10">
            <tr>
              <th className="px-2 py-1.5 text-left w-8">P</th>
              <th className="px-2 py-1.5 text-left">CYCLE</th>
              <th className="px-2 py-1.5 text-right">SCAN</th>
              <th className="px-2 py-1.5 text-right">SIG</th>
              <th className="px-2 py-1.5 text-right">FILL</th>
              <th className="px-2 py-1.5 text-right">P&L</th>
            </tr>
          </thead>
          <tbody>
            {ranked.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="hud-label text-center py-6 text-f1-gray"
                >
                  NO SESSIONS YET
                </td>
              </tr>
            )}
            {ranked.map((s, i) => {
              const pnl = s.session_pnl ?? 0;
              const up = pnl > 0;
              const down = pnl < 0;
              return (
                <tr
                  key={`${s.timestamp}-${i}`}
                  className="border-b border-f1-chalk/5 hover:bg-f1-red/5"
                >
                  <td className="px-2 py-1.5">
                    <span
                      className={`inline-flex items-center justify-center w-6 h-6 rounded-full border ${
                        i === 0
                          ? "border-f1-red text-f1-red text-glow-red"
                          : i < 3
                            ? "border-f1-gold text-f1-gold"
                            : "border-f1-chalk/20 text-f1-chalk/60"
                      } text-[10px]`}
                    >
                      {i + 1}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-f1-chalk/80">
                    {fmtTimeAgo(s.timestamp)}
                  </td>
                  <td className="px-2 py-1.5 text-right text-f1-chalk/80 tabular-nums">
                    {s.markets_scanned}
                  </td>
                  <td className="px-2 py-1.5 text-right text-f1-chalk/80 tabular-nums">
                    {s.signals_generated}
                  </td>
                  <td className="px-2 py-1.5 text-right text-f1-chalk/80 tabular-nums">
                    {s.trades_executed}
                  </td>
                  <td
                    className={`px-2 py-1.5 text-right tabular-nums ${
                      up ? "text-f1-mint" : down ? "text-f1-red" : "text-f1-chalk/70"
                    }`}
                  >
                    {fmtMoney(pnl)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
