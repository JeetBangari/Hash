import yfinance as yf
import pandas as pd
import pandas_ta as ta
from crewai.tools import tool

@tool("Fetch Live Stock Data")
def fetch_stock_price(ticker: str) -> str:
    """Fetches the current live price and 6-month historical data summary for a given stock ticker."""
    stock = yf.Ticker(ticker)
    data = stock.history(period="1mo")
    
    if data.empty:
        return f"Could not fetch data for {ticker}. Ensure the ticker symbol is correct (e.g., RELIANCE.NS for NSE)."
    
    current_price = data['Close'].iloc[-1]
    return f"The current live adjusted price of {ticker} is ₹{current_price:.2f}."

@tool("Calculate Technical Indicators")
def calculate_technical_indicators(ticker: str) -> str:
    """Calculates the Average True Range (ATR) for dynamic Stop Loss and the MACD for trend direction."""
    stock = yf.Ticker(ticker)
    data = stock.history(period="6mo")
    
    if data.empty:
        return "Data fetch failed. Cannot calculate indicators."
    
    # Calculate ATR (14 period) for volatility-based Stop Loss
    data.ta.atr(length=14, append=True)
    # Calculate MACD for trend momentum
    data.ta.macd(append=True)
    
    latest = data.iloc[-1]
    atr_value = latest['ATRr_14']
    macd_value = latest['MACD_12_26_9']
    signal_value = latest['MACDs_12_26_9']
    
    trend = "Bullish (Upward)" if macd_value > signal_value else "Bearish (Downward)"
    
    return f"Technical Indicators for {ticker}: The 14-day ATR is {atr_value:.2f}. The current MACD trend is {trend}."

@tool("Fetch Market News")
def fetch_stock_news(ticker: str) -> str:
    """Fetches the latest news headlines and sentiment context for a given stock ticker."""
    stock = yf.Ticker(ticker)
    news = stock.news
    
    if not news:
        return f"No recent news found for {ticker}."
    
    # Extract the top 4 news headlines
    headlines = [item['title'] for item in news[:4]]
    return f"Latest news headlines for {ticker}: " + " | ".join(headlines)

@tool("Calculate Risk and Targets")
def calculate_risk_and_targets(ticker: str) -> str:
    """Calculates exact Stop Loss, Target Prices, and Time Horizon based on ATR volatility."""
    stock = yf.Ticker(ticker)
    data = stock.history(period="3mo")
    
    if data.empty:
        return "Data fetch failed. Cannot calculate risk."
    
    # Calculate ATR
    data.ta.atr(length=14, append=True)
    latest = data.iloc[-1]
    current_price = latest['Close']
    atr_value = latest['ATRr_14']
    
    # Mathematical Risk Engine Logic
    # We use a 1.5x ATR multiplier for the Stop Loss, and a 1:2 Risk-to-Reward for the Target
    stop_loss = current_price - (1.5 * atr_value)
    target_price = current_price + (3.0 * atr_value)
    
    # Time Horizon Logic based on Volatility Percentage
    volatility_pct = (atr_value / current_price) * 100
    
    if volatility_pct > 3.0:
        time_horizon = "Short-Term (1-3 Months)"
    elif volatility_pct > 1.5:
        time_horizon = "Medium-Term (3-6 Months)"
    else:
        time_horizon = "Long-Term (6-12+ Months)"
        
    return (
        f"Risk Engine Output for {ticker} (Current Price: ₹{current_price:.2f}):\n"
        f"- Strict Stop Loss: ₹{stop_loss:.2f}\n"
        f"- Target Price: ₹{target_price:.2f}\n"
        f"- Asset Volatility: {volatility_pct:.2f}%\n"
        f"- System Suggested Time Horizon: {time_horizon}"
    )

@tool("Fetch Financial Metrics")
def fetch_financial_metrics(ticker: str) -> str:
    """Fetches key financial ratios and Wall Street analyst recommendations for a stock."""
    stock = yf.Ticker(ticker)
    info = stock.info
    
    if not info:
        return "Could not fetch financial metrics."
    
    # Safely extract metrics (using .get() prevents errors if data is missing)
    pe_ratio = info.get('forwardPE', 'N/A')
    market_cap = info.get('marketCap', 'N/A')
    fifty_two_high = info.get('fiftyTwoWeekHigh', 'N/A')
    fifty_two_low = info.get('fiftyTwoWeekLow', 'N/A')
    recommendation = info.get('recommendationKey', 'none').replace('_', ' ').title()
    
    return (
        f"Financial Metrics for {ticker}:\n"
        f"- Forward P/E Ratio: {pe_ratio}\n"
        f"- Market Cap: {market_cap}\n"
        f"- 52-Week High: ₹{fifty_two_high}\n"
        f"- 52-Week Low: ₹{fifty_two_low}\n"
        f"- Wall Street Analyst Consensus: {recommendation}"
    )