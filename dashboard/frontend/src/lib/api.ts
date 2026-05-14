export interface Snapshot {
  ts: string;
  standby?: boolean;
  reason?: string;
  portfolio: {
    current_balance: number;
    starting_balance: number;
    total_pnl: number;
    total_pnl_pct: number;
    daily_pnl: number;
    open_positions: number;
    win_rate: number;
    total_trades: number;
    winning_trades?: number;
    losing_trades?: number;
    peak_balance: number;
    current_drawdown: number;
    max_drawdown?: number;
    sharpe_ratio?: number | null;
    average_win?: number;
    average_loss?: number;
    largest_win?: number;
    largest_loss?: number;
  };
  positions: Array<{
    position_id: string;
    ticker: string;
    market_title?: string;
    category?: string;
    side: string;
    quantity: number;
    entry_price: number;
    current_price?: number;
    stop_loss?: number;
    take_profit?: number;
    unrealized_pnl?: number;
    unrealized_pnl_percent?: number;
    price_delta?: number;
    price_delta_pct?: number;
    opened_at: string;
  }>;
  trades_recent: Array<{
    timestamp: string;
    ticker: string;
    market_title?: string;
    category?: string;
    side: string;
    action: string;
    quantity: number;
    price: number;
    total_cost: number;
    realized_pnl?: number;
    pnl_percent?: number;
    signal_confidence?: number;
    decision_path?: string;
  }>;
  sessions_recent: Array<{
    timestamp: string;
    markets_scanned: number;
    signals_generated: number;
    trades_executed: number;
    starting_balance?: number;
    ending_balance?: number;
    session_pnl?: number;
    circuit_breaker_triggered?: boolean;
    circuit_breaker_reason?: string;
    opportunities_analyzed?: unknown;
    decision_path?: string;
  }>;
  decisions_recent: Array<{
    id: number;
    created_at: string;
    ticker: string;
    decision_path?: string;
    judge_decision?: {
      signal: "LONG" | "SHORT" | "NO_TRADE" | string;
      confidence: number;
      calibrated_probability: number;
      expected_return_pct: number;
      kelly_fraction: number;
      market_edge?: string;
      reasoning?: string;
      key_factors?: string[];
      risk_factors?: string[];
      debate_winner?: string;
    } | null;
    calibrated_probability?: number;
    recalled_lesson_ids?: number[];
    thinking_tokens_used?: number;
    final_pnl?: number;
    outcome_label?: string;
  }>;
  lessons_recent: Array<{
    id: number;
    created_at: string;
    ticker?: string;
    category?: string;
    lesson_type: string;
    text: string;
    outcome_pnl?: number;
    source_agent?: string;
  }>;
  agentic_status: {
    decision_path: string;
    shadow_legacy: boolean;
    judge_model: string;
    specialist_model: string;
    cheap_model: string;
    enable_web_search: boolean;
    enable_debate: boolean;
    enable_memory: boolean;
    enable_extended_thinking: boolean;
    trading_mode: string;
    starting_capital: number;
  };
  markets_ticker: Array<{
    ticker: string;
    title?: string;
    category?: string;
    yes_bid: number;
    yes_ask: number;
    no_bid: number;
    no_ask: number;
    volume_24h?: number;
    open_interest?: number;
    timestamp: string;
  }>;
}

export async function fetchSnapshot(): Promise<Snapshot> {
  const res = await fetch("/api/snapshot", { cache: "no-store" });
  if (!res.ok) throw new Error(`snapshot ${res.status}`);
  return (await res.json()) as Snapshot;
}
