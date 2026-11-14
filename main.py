from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import os
import yfinance as yf
import json
import math
import requests
from datetime import datetime, timedelta
import urllib.parse
import xml.etree.ElementTree as ET
from openai import OpenAI
from crew import ShareMarketCrew
import auth
from dotenv import load_dotenv
import bcrypt
import joblib
import pandas as pd
import numpy as np
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 🧠 QUANT MODEL INITIALIZATION & MATH LOGIC
# ==========================================
try:
    quant_model = joblib.load("quant_model.joblib")
    print("🧠 Quant Model successfully loaded into FastAPI!")
except Exception as e:
    print("⚠️ Warning: Could not load quant_model.joblib. Make sure it is in the same folder.")
    quant_model = None

def get_live_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_live_atr(df, window=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(window).mean()

def get_quant_prediction(ticker: str) -> str:
    if not quant_model:
        return "Error: Internal Quant Model is currently offline."
        
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        
        if len(df) < 200:
            return f"Error: Not enough historical data to run the quant model on {ticker}."
            
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        df['RSI_14'] = get_live_rsi(df['Close'])
        
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        df['BB_Std'] = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['SMA_20'] + (df['BB_Std'] * 2)
        df['BB_Lower'] = df['SMA_20'] - (df['BB_Std'] * 2)
        df['BB_Position'] = (df['Close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'])
        
        df['ATR_14'] = get_live_atr(df)
        
        df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA_20']
        df['Daily_Return_Pct'] = df['Close'].pct_change() * 100
        
        latest_data = df.iloc[-1:]
        
        features = ['SMA_20', 'SMA_50', 'SMA_200', 'RSI_14', 'MACD', 'MACD_Signal', 'Daily_Return_Pct', 'BB_Position', 'ATR_14', 'Volume_Ratio']
        X_live = latest_data[features]
        
        probability_up = quant_model.predict_proba(X_live)[0][1] * 100
        
        if probability_up > 55:
            sentiment = "STRONG BULLISH EDGE"
        elif probability_up < 45:
            sentiment = "STRONG BEARISH EDGE"
        else:
            sentiment = "NEUTRAL / NO CLEAR EDGE"
            
        return f"QUANT MODEL RESULT FOR {ticker}: {probability_up:.1f}% probability of gaining >2% in the next 14 days. System Status: {sentiment}."
        
    except Exception as e:
        return f"Error running quant model: {str(e)}"

# ==========================================
# 📋 PYDANTIC MODELS
# ==========================================
class OTPRequest(BaseModel): email: str; otp: str
class AnalyzeRequest(BaseModel): tickers: List[str]
class UserDataRequest(BaseModel): email: str
class TradeRequest(BaseModel): email: str; ticker: str; action: str; quantity: int; stop_loss: float; target_price: float
class WatchlistRequest(BaseModel): email: str; ticker: str
class WatchlistDataRequest(BaseModel): email: str
class FundRequest(BaseModel): email: str; amount: float
class AdminProcessRequest(BaseModel): email: str; target_email: str; timestamp: str; action: str
class ChatRequest(BaseModel): email: str; prompt: str; messages: List[Dict[str, str]]
class PortfolioRequest(BaseModel): email: str; mode: str
class SignupRequest(BaseModel): name: str; email: str; password: str
class LoginRequest(BaseModel): email: str; password: str

# ==========================================
# 🔐 AUTH ENDPOINTS
# ==========================================
@app.post("/api/signup")
def signup(request: SignupRequest):
    if auth.users_collection.find_one({"email": request.email}):
        raise HTTPException(status_code=400, detail="User with this email already exists.")

    salt = bcrypt.gensalt()
    hashed_password_bytes = bcrypt.hashpw(request.password.encode('utf-8'), salt)

    new_user = {
        "name": request.name,
        "email": request.email,
        "password": hashed_password_bytes,  
        "role": "user",
        "virtual_balance": 100000.0, 
        "live_balance": 0.0,
        "demo_portfolio": {},
        "live_portfolio": {},
        "demo_order_history": [],
        "live_order_history": [],
        "watchlist": ["RELIANCE.NS", "TCS.NS"] 
    }
    
    auth.users_collection.insert_one(new_user)
    return {"status": "success", "message": "Account created securely!"}

@app.post("/api/login")
def login(request: LoginRequest, background_tasks: BackgroundTasks):
    success, result = auth.verify_credentials(request.email, request.password)
    if success:
        # Send OTP asynchronously in the background for instant response
        background_tasks.add_task(auth.generate_and_store_otp, request.email)
        return {"status": "success", "message": "OTP Sent"}
    raise HTTPException(status_code=401, detail=result)

@app.post("/api/verify-otp")
def verify_otp(request: OTPRequest):
    success, msg = auth.verify_otp(request.email, request.otp)
    if success:
        user_data = auth.users_collection.find_one({"email": request.email}, {"_id": 0, "password": 0})
        return {"status": "success", "user_data": user_data}
    raise HTTPException(status_code=401, detail=msg)

@app.post("/api/user-data")
def get_user_data(request: UserDataRequest):
    user_data = auth.users_collection.find_one({"email": request.email}, {"_id": 0, "password": 0})
    if user_data: return {"status": "success", "user_data": user_data}
    raise HTTPException(status_code=404, detail="User not found")

# ==========================================
# 📈 TERMINAL & MARKET ENDPOINTS
# ==========================================
@app.post("/api/analyze")
def analyze_stocks(request: AnalyzeRequest):
    results = {}
    for ticker in request.tickers:
        ticker = ticker.upper()
        if "." not in ticker: ticker += ".NS"
        stock = yf.Ticker(ticker)
        
        try:
            info = stock.info
            live_price = round(stock.fast_info.last_price, 2)
        except:
            info = {}
            live_price = 0.0

        try:
            hist_df = stock.history(period="6mo").dropna(subset=['Open', 'High', 'Low', 'Close'])
            chart_data = []
            for date_index, row in hist_df.iterrows():
                if math.isnan(row['Close']) or math.isnan(row['Open']): continue
                chart_data.append({
                    "time": date_index.strftime('%Y-%m-%d'),
                    "open": float(round(row['Open'], 2)),
                    "high": float(round(row['High'], 2)),
                    "low": float(round(row['Low'], 2)),
                    "close": float(round(row['Close'], 2))
                })
        except Exception as e:
            chart_data = []

        ai_data = auth.get_cached_analysis(ticker)
        if not ai_data:
            try:
                inputs = {'ticker': ticker}
                res = ShareMarketCrew().crew().kickoff(inputs=inputs)
                ai_data = res.pydantic.model_dump() if hasattr(res, 'pydantic') and res.pydantic else json.loads(res.raw)
                auth.save_analysis_to_cache(ticker, ai_data)
            except Exception as e:
                ai_data = {"error": str(e), "decision": "AI Offline", "target_price": "-", "stop_loss": "-", "fundamental_reasoning": "AI Analysis unavailable."}

        results[ticker] = {"live_price": live_price, "market_cap": info.get("marketCap", "N/A"), "chart_data": chart_data, "ai_analysis": ai_data}
    return {"status": "success", "data": results}

@app.get("/api/market-updates")
def get_market_updates(query: str = ""):
    api_key = os.getenv("NEWS_API_KEY")
    articles = []

    if api_key and len(api_key) == 32: 
        try:
            if query:
                url = f"https://newsapi.org/v2/everything?q={query}&language=en&sortBy=relevancy&apiKey={api_key}"
            else:
                url = f"https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey={api_key}"
            
            resp = requests.get(url).json()
            if resp.get("status") == "ok":
                for a in resp.get("articles", []):
                    if a.get('title') and '[Removed]' not in a.get('title'):
                        articles.append({"title": a['title'], "url": a['url']})
                if articles:
                    return {"articles": articles[:5]}
        except Exception as e:
            print("NewsAPI Error:", e)

    if api_key:
        try:
            if query:
                symbol = query.upper()
                if "." not in symbol: symbol += ".NS"
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                url = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from={start_date}&to={end_date}&token={api_key}"
            else:
                url = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
                
            resp = requests.get(url).json()
            if isinstance(resp, list):
                for a in resp[:5]:
                    if a.get('headline') and a.get('url'):
                        articles.append({"title": a['headline'], "url": a['url']})
                if articles:
                    return {"articles": articles}
        except Exception as e:
            print("Finnhub Error:", e)

    try:
        search_term = query if query else "Indian Stock Market"
        encoded_query = urllib.parse.quote(search_term + " stock")
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            for item in root.findall('.//item')[:5]:
                title_elem = item.find('title')
                link_elem = item.find('link')
                if title_elem is not None and link_elem is not None:
                    title = title_elem.text
                    link = link_elem.text
                    clean_title = title.rsplit(' - ', 1)[0] if ' - ' in title else title
                    articles.append({"title": clean_title, "url": link})
            if articles:
                return {"articles": articles}
    except Exception as e:
        print("Google News RSS Error:", e)
        
    return {"articles": []}

# ==========================================
# 💼 ACCOUNT ACTION ENDPOINTS
# ==========================================
@app.post("/api/trade")
def execute_trade(request: TradeRequest):
    try:
        current_price = round(yf.Ticker(request.ticker).fast_info.last_price, 2)
    except:
        raise HTTPException(status_code=400, detail="Could not fetch live price for execution.")
        
    success, msg, user = auth.execute_dummy_trade(
        request.email, request.ticker, request.action, request.quantity, current_price, request.stop_loss, request.target_price
    )
    if success: return {"status": "success", "message": msg, "user_data": user}
    raise HTTPException(status_code=400, detail=msg)

@app.post("/api/portfolio-data")
def get_portfolio_data(request: PortfolioRequest):
    user = auth.users_collection.find_one({"email": request.email})
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    portfolio_key = "demo_portfolio" if request.mode == "demo" else "live_portfolio"
    portfolio = user.get(portfolio_key, {})
    
    enriched_data = []
    for ticker, details in portfolio.items():
        shares = details.get("shares", 0)
        avg_price = details.get("avg_price", 0.0)
        
        stop_loss = details.get("stop_loss", 0.0)
        target_price = details.get("target_price", 0.0)
        
        try:
            live_price = round(yf.Ticker(ticker).fast_info.last_price, 2)
        except:
            live_price = avg_price
        
        invested = shares * avg_price
        current_value = shares * live_price
        pnl = current_value - invested
        pnl_pct = (pnl / invested) * 100 if invested > 0 else 0.0
        
        enriched_data.append({
            "ticker": ticker,
            "shares": shares,
            "avg_price": round(avg_price, 2),
            "live_price": live_price,
            "stop_loss": stop_loss,
            "target_price": target_price,
            "invested": round(invested, 2),
            "current_value": round(current_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2)
        })
    return {"status": "success", "portfolio": enriched_data}

@app.post("/api/watchlist-data")
def get_watchlist_data(request: WatchlistDataRequest):
    user = auth.users_collection.find_one({"email": request.email})
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    watchlist = user.get("watchlist", [])
    data = []
    for t in watchlist:
        try:
            stock = yf.Ticker(t)
            live_p = round(stock.fast_info.last_price, 2)
            prev_close = round(stock.fast_info.previous_close, 2)
            change = live_p - prev_close
            pct_change = (change / prev_close) * 100
            data.append({
                "ticker": t,
                "live_price": live_p,
                "change": round(change, 2),
                "pct_change": round(pct_change, 2)
            })
        except:
            data.append({
                "ticker": t,
                "live_price": 0.0,
                "change": 0.0,
                "pct_change": 0.0
            })
    return {"status": "success", "watchlist": data}

@app.post("/api/watchlist")
def toggle_watchlist(request: WatchlistRequest):
    success, msg, user = auth.toggle_watchlist(request.email, request.ticker)
    if success: return {"status": "success", "message": msg, "user_data": user}
    raise HTTPException(status_code=400, detail=msg)

@app.post("/api/fund-request")
def request_funds(request: FundRequest):
    success, msg, user = auth.submit_fund_request(request.email, request.amount)
    if success: return {"status": "success", "message": msg, "user_data": user}
    raise HTTPException(status_code=400, detail=msg)

@app.get("/api/admin/requests")
def get_admin_requests(email: str):
    user = auth.users_collection.find_one({"email": email})
    if not user or user.get("role") != "admin": raise HTTPException(status_code=403, detail="Unauthorized")
    return {"requests": auth.get_all_pending_requests()}

@app.post("/api/admin/process")
def process_admin_request(request: AdminProcessRequest):
    user = auth.users_collection.find_one({"email": request.email})
    if not user or user.get("role") != "admin": raise HTTPException(status_code=403, detail="Unauthorized")
    success = auth.process_fund_request(request.target_email, request.timestamp, request.action)
    if success: return {"status": "success"}
    raise HTTPException(status_code=400, detail="Failed to process request")

# ==========================================
# 🤖 UPGRADED AI AGENT (NEURO-SYMBOLIC LLM)
# ==========================================
@app.post("/api/chat")
def chat_with_ai(request: ChatRequest):
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key: raise HTTPException(status_code=500, detail="OpenAI Key Missing")
    
    user = auth.users_collection.find_one({"email": request.email})
    if not user: raise HTTPException(status_code=404, detail="User not found")

    system_prompt = f"""You are an elite, highly decisive quantitative Wealth Manager for {user.get('name')}. 
    You have direct access to their account and our proprietary internal Machine Learning Quant Model.
    
    CRITICAL RULES: 
    1. NEVER quote a stock price from your memory. If you suggest a stock to the user, you MUST use the `get_live_price` tool to check its exact real-time price first.
    2. If a user asks for advice on buying or selling, you MUST use the `get_quant_prediction` tool to get the mathematical probability of success. 
    3. Base your advice strictly on the Quant Model's percentage. If the probability is above 55%, tell them to BUY or HOLD. If it is below 45%, tell them to SELL or place a stop-loss. 
    
    Be sharp, confident, and mathematical. Always format stock tickers with .NS if they are Indian stocks."""
    
    messages = [{"role": "system", "content": system_prompt}] + request.messages + [{"role": "user", "content": request.prompt}]
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_live_price",
                "description": "Get the real-time live market price of a stock ticker.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "The stock ticker symbol (e.g., RELIANCE.NS, SUZLON.NS)"}
                    },
                    "required": ["ticker"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_quant_prediction",
                "description": "Get the live Machine Learning probability of a stock going up in the next 14 days.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "The stock ticker symbol (e.g., RELIANCE.NS)"}
                    },
                    "required": ["ticker"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_portfolio",
                "description": "Get the user's current virtual cash balance, watchlist, and portfolio holdings.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "execute_trade",
                "description": "Execute a paper trade (BUY or SELL) for the user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "The stock ticker symbol (e.g., RELIANCE.NS, TCS.NS)"},
                        "action": {"type": "string", "enum": ["BUY", "SELL"]},
                        "quantity": {"type": "integer", "description": "The number of shares to trade"}
                    },
                    "required": ["ticker", "action", "quantity"]
                }
            }
        }
    ]

    try:
        client = OpenAI(api_key=openai_api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        if tool_calls:
            messages.append(response_message) 
            
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                if function_name == "get_live_price":
                    ticker = function_args.get("ticker").upper()
                    if "." not in ticker: ticker += ".NS"
                    try:
                        current_price = round(yf.Ticker(ticker).fast_info.last_price, 2)
                        function_response = f"The real-time live market price of {ticker} is ₹{current_price}."
                    except Exception as e:
                        function_response = f"Error: Could not fetch live price for {ticker}."

                elif function_name == "get_quant_prediction":
                    ticker = function_args.get("ticker").upper()
                    if "." not in ticker: ticker += ".NS"
                    function_response = get_quant_prediction(ticker)

                elif function_name == "get_portfolio":
                    portfolio_data = {
                        "virtual_balance": user.get("virtual_balance", 0.0),
                        "watchlist": user.get("watchlist", []),
                        "holdings": user.get("demo_portfolio", {})
                    }
                    function_response = json.dumps(portfolio_data)
                    
                elif function_name == "execute_trade":
                    ticker = function_args.get("ticker").upper()
                    if "." not in ticker: ticker += ".NS"
                    
                    try:
                        current_price = round(yf.Ticker(ticker).fast_info.last_price, 2)
                        success, msg, updated_user = auth.execute_dummy_trade(
                            request.email, ticker, function_args.get("action"), 
                            function_args.get("quantity"), current_price
                        )
                        function_response = msg
                    except Exception as e:
                        function_response = f"Trade failed. Could not fetch live price for {ticker}."
                else:
                    function_response = "Error: Unknown tool."

                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                })

            second_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            return {"response": second_response.choices[0].message.content}

        return {"response": response_message.content}

    except Exception as e:
        print("Chatbot Error:", e)
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 🌐 FRONTEND HOSTING
# ==========================================
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse("index.html")
