"""
External Odds Comparison Utility

Compares our AI-generated signals against external sources:
- Vegas lines (sports)
- Polymarket (politics/crypto)
- Fed Funds Futures (economics)

Only trade when our model differs from consensus by a meaningful margin,
otherwise we're just paying fees to match the market.

Research: Most profitable prediction market traders identify MISPRICINGS,
not just correct predictions. Getting the same answer as Vegas means no edge.
"""
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import requests
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExternalOdds:
    """External odds from a source"""
    source: str
    probability: float  # 0-1
    timestamp: datetime
    raw_data: Optional[Dict] = None
    error: Optional[str] = None


@dataclass
class EdgeAnalysis:
    """Analysis of edge between our signal and external odds"""
    our_probability: float
    external_probability: float
    edge_pct: float  # Positive = we're more bullish than external
    has_meaningful_edge: bool
    recommendation: str  # 'trade', 'skip', 'reverse'
    explanation: str


class ExternalOddsComparison:
    """
    Compares our signals against external odds sources
    
    Key insight: If your model says 60% and Vegas says 60%, you have NO EDGE.
    Edge = difference between your estimate and market consensus.
    """
    
    def __init__(self):
        # Minimum edge required to trade (10% difference)
        self.min_edge_pct = 10.0
        
        # Consider reversing if we're very wrong vs consensus
        self.reverse_threshold_pct = -15.0
        
        # Category to source mapping
        self.category_sources = {
            'sports': ['vegas'],
            'politics': ['polymarket', 'predictit'],
            'economics': ['fed_futures', 'polymarket'],
            'crypto': ['polymarket', 'coingecko'],
            'finance': ['polymarket'],
            'weather': []  # No good external source
        }
    
    def get_external_odds(
        self,
        ticker: str,
        title: str,
        category: str
    ) -> Optional[ExternalOdds]:
        """
        Get external odds for a market
        
        Args:
            ticker: Kalshi ticker
            title: Market question
            category: Market category
            
        Returns:
            External odds if available
        """
        sources = self.category_sources.get(category, [])
        
        for source in sources:
            try:
                if source == 'vegas':
                    odds = self._get_vegas_odds(ticker, title)
                elif source == 'polymarket':
                    odds = self._get_polymarket_odds(ticker, title)
                elif source == 'fed_futures':
                    odds = self._get_fed_futures_odds(ticker, title)
                else:
                    continue
                
                if odds and not odds.error:
                    return odds
                    
            except Exception as e:
                logger.warning(f"Error fetching {source} odds: {e}")
                continue
        
        return None
    
    def analyze_edge(
        self,
        our_confidence: float,
        our_signal: str,
        external_odds: Optional[ExternalOdds]
    ) -> EdgeAnalysis:
        """
        Analyze whether we have edge vs external consensus
        
        Args:
            our_confidence: Our signal confidence (0-100)
            our_signal: 'LONG' or 'SHORT'
            external_odds: External probability if available
            
        Returns:
            Edge analysis with recommendation
        """
        our_probability = our_confidence / 100.0
        
        # Adjust for signal direction
        if our_signal == 'SHORT':
            our_probability = 1 - our_probability
        
        if external_odds is None:
            # No external data - can still trade but note the risk
            return EdgeAnalysis(
                our_probability=our_probability,
                external_probability=0.5,  # Assume 50/50 if unknown
                edge_pct=abs(our_probability - 0.5) * 100,
                has_meaningful_edge=our_confidence >= 65,  # Higher bar without external validation
                recommendation='trade' if our_confidence >= 65 else 'skip',
                explanation="No external odds available - requiring higher confidence threshold"
            )
        
        external_prob = external_odds.probability
        edge_pct = (our_probability - external_prob) * 100
        
        # Determine recommendation
        if abs(edge_pct) >= self.min_edge_pct:
            if edge_pct > 0:
                recommendation = 'trade'
                explanation = (
                    f"EDGE CONFIRMED: We estimate {our_probability:.0%} vs "
                    f"{external_odds.source} at {external_prob:.0%}. "
                    f"Edge: {edge_pct:+.1f}% - proceed with trade."
                )
            else:
                # We're more bearish, but signal is LONG? Or vice versa
                recommendation = 'trade'
                explanation = (
                    f"CONTRARIAN EDGE: We're {abs(edge_pct):.1f}% more "
                    f"{'bullish' if edge_pct > 0 else 'bearish'} than {external_odds.source}. "
                    f"Proceed with caution."
                )
            has_edge = True
            
        elif edge_pct <= self.reverse_threshold_pct:
            # We're significantly wrong vs consensus - consider reversing
            recommendation = 'reverse'
            explanation = (
                f"WARNING: {external_odds.source} strongly disagrees. "
                f"They estimate {external_prob:.0%} vs our {our_probability:.0%}. "
                f"Consider reversing or skipping."
            )
            has_edge = False
            
        else:
            # No meaningful edge
            recommendation = 'skip'
            explanation = (
                f"NO EDGE: Our estimate ({our_probability:.0%}) matches "
                f"{external_odds.source} ({external_prob:.0%}). "
                f"Edge too small ({edge_pct:+.1f}%) - skip to avoid fee drag."
            )
            has_edge = False
        
        logger.info(explanation)
        
        return EdgeAnalysis(
            our_probability=our_probability,
            external_probability=external_prob,
            edge_pct=edge_pct,
            has_meaningful_edge=has_edge,
            recommendation=recommendation,
            explanation=explanation
        )
    
    def _get_vegas_odds(self, ticker: str, title: str) -> Optional[ExternalOdds]:
        """
        Get Vegas odds for sports markets
        
        In production, integrate with:
        - The Odds API (https://the-odds-api.com/)
        - ESPN API
        - Direct sportsbook feeds
        """
        # Check if this is a sports market
        sports_keywords = ['win', 'beat', 'game', 'match', 'championship', 'playoff']
        if not any(kw in title.lower() for kw in sports_keywords):
            return None
        
        # Mock implementation - in production, call actual API
        # Example: The Odds API provides free tier
        try:
            # Placeholder for actual API integration
            # response = requests.get(
            #     f"https://api.the-odds-api.com/v4/sports/...",
            #     params={"apiKey": settings.odds_api_key}
            # )
            
            # For now, return None to indicate no data
            # This will cause the system to require higher confidence
            logger.debug(f"Vegas odds lookup not implemented for: {ticker}")
            return None
            
        except Exception as e:
            return ExternalOdds(
                source='vegas',
                probability=0.0,
                timestamp=datetime.utcnow(),
                error=str(e)
            )
    
    def _get_polymarket_odds(self, ticker: str, title: str) -> Optional[ExternalOdds]:
        """
        Get Polymarket odds for similar markets
        
        Polymarket has public GraphQL API for market data
        """
        try:
            # Polymarket GraphQL endpoint
            # Note: Need to find matching market by title similarity
            
            # Placeholder - in production implement NLP matching
            # to find the corresponding Polymarket market
            logger.debug(f"Polymarket lookup not implemented for: {ticker}")
            return None
            
        except Exception as e:
            return ExternalOdds(
                source='polymarket',
                probability=0.0,
                timestamp=datetime.utcnow(),
                error=str(e)
            )
    
    def _get_fed_futures_odds(self, ticker: str, title: str) -> Optional[ExternalOdds]:
        """
        Get Fed Funds Futures implied probabilities
        
        CME FedWatch tool methodology for rate decisions
        """
        fed_keywords = ['fed', 'fomc', 'rate', 'interest', 'basis point', 'bps']
        if not any(kw in title.lower() for kw in fed_keywords):
            return None
        
        try:
            # CME FedWatch provides implied probabilities
            # In production, scrape or use CME data API
            
            # Placeholder
            logger.debug(f"Fed Futures lookup not implemented for: {ticker}")
            return None
            
        except Exception as e:
            return ExternalOdds(
                source='fed_futures',
                probability=0.0,
                timestamp=datetime.utcnow(),
                error=str(e)
            )


# Global instance
external_odds_comparison = ExternalOddsComparison()


def validate_edge_before_trading(
    ticker: str,
    title: str,
    category: str,
    our_confidence: float,
    our_signal: str
) -> Tuple[bool, str, EdgeAnalysis]:
    """
    Convenience function to validate edge before trading
    
    Returns:
        (should_proceed, reason, edge_analysis)
    """
    external = external_odds_comparison.get_external_odds(ticker, title, category)
    analysis = external_odds_comparison.analyze_edge(our_confidence, our_signal, external)
    
    if analysis.recommendation == 'trade':
        return True, analysis.explanation, analysis
    elif analysis.recommendation == 'reverse':
        return False, f"REVERSE SIGNAL: {analysis.explanation}", analysis
    else:
        return False, analysis.explanation, analysis
