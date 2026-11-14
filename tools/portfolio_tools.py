import json
from crewai.tools import tool

@tool("Fetch User Portfolio")
def fetch_user_portfolio(user_id: str = "default") -> str:
    """Fetches the user's current brokerage holdings, cash balance, and risk profile from the database."""
    # Simulating a secure broker API response
    portfolio_data = {
        "account_holder": "Jeet Bangari",
        "available_cash": 15000.00,
        "risk_profile": "Aggressive",
        "monthly_sip_budget": 5000.00,
        "holdings": {
            "ZOMATO.NS": {"shares": 50, "avg_price": 75.00},
            "TCS.NS": {"shares": 2, "avg_price": 3800.00}
        }
    }
    return json.dumps(portfolio_data, indent=2)

@tool("Calculate Smart SIP")
def calculate_smart_sip(ticker: str, current_price: float, volatility_pct: float) -> str:
    """Calculates a Smart SIP amount. Invests more during dips (high volatility) and standard amounts during stable trends."""
    base_sip = 5000.00 
    
    # Smart SIP Logic: If volatility is high (> 2.0%), the market is likely correcting/dipping. 
    # We increase the SIP to accumulate more units at a cheaper price.
    if volatility_pct > 2.0:
        adjusted_sip = base_sip * 1.20 # 20% bump to buy the dip
        rationale = "Market is highly volatile/correcting. Increasing SIP by 20% to accumulate more units at lower prices."
    else:
        adjusted_sip = base_sip
        rationale = "Market volatility is stable. Proceeding with standard base SIP."

    return f"Smart SIP Recommendation for {ticker}: ₹{adjusted_sip:.2f}. Logic: {rationale}"