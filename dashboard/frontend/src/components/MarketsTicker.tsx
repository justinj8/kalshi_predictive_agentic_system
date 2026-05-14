import { fmtPrice, fmtTicker } from "../lib/format";
import type { Snapshot } from "../lib/api";

interface Props {
  markets: Snapshot["markets_ticker"];
  online: boolean;
}

/**
 * Broadcast-style scrolling marquee across the top of the screen.
 * Shows each market's YES/NO and a colored chip for spread quality.
 */
export function MarketsTicker({ markets, online }: Props) {
  // Pad with placeholders so the marquee always has content.
  const items =
    markets.length > 0
      ? [...markets, ...markets]
      : [
          {
            ticker: "STANDBY",
            title: "Waiting for first trading cycle",
            yes_ask: 0,
            yes_bid: 0,
            no_ask: 0,
            no_bid: 0,
          } as Snapshot["markets_ticker"][number],
        ];

  return (
    <div className="relative w-full h-9 overflow-hidden border-y border-f1-chalk/10 bg-ink-900/60 flex items-center">
      <div className="flex items-center gap-3 px-3 border-r border-f1-chalk/10 h-full bg-f1-red/95 text-ink-950 font-display text-xs tracking-[0.32em] shrink-0">
        {online ? (
          <>
            <span className="rec-dot bg-ink-950" />
            LIVE&nbsp;·&nbsp;KALSHI
          </>
        ) : (
          <>OFFLINE&nbsp;·&nbsp;NO&nbsp;FEED</>
        )}
      </div>

      <div className="relative flex-1 overflow-hidden h-full">
        <div className="marquee-track h-full items-center animate-marquee whitespace-nowrap pl-6">
          {items.map((m, i) => {
            const spread =
              m.yes_ask > 0 && m.yes_bid > 0 ? (m.yes_ask - m.yes_bid) * 100 : 0;
            const dotColor =
              spread <= 2
                ? "bg-f1-mint"
                : spread <= 5
                  ? "bg-f1-gold"
                  : "bg-f1-red";
            return (
              <div
                key={`${m.ticker}-${i}`}
                className="flex items-center gap-2 text-xs font-mono"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
                <span className="font-display tracking-wider">
                  {fmtTicker(m.ticker)}
                </span>
                <span className="text-f1-mint">
                  YES&nbsp;{fmtPrice(m.yes_ask)}
                </span>
                <span className="text-f1-red">NO&nbsp;{fmtPrice(m.no_ask)}</span>
                <span className="text-f1-gray">·</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
