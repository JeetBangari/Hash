import os
import random
import requests
from datetime import datetime, timedelta
from pymongo import MongoClient
import bcrypt
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 🗄️ DATABASE CONNECTION
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.get_default_database()

users_collection = db["users"]
cache_collection = db["ai_analysis_cache"]

# ==========================================
# 🔐 AUTHENTICATION & OTP LOGIC
# ==========================================
def verify_credentials(email, password):
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "User not found. Please create an account."
    
    if bcrypt.checkpw(password.encode('utf-8'), user['password']):
        return True, "Valid credentials"
    
    return False, "Invalid password"

def generate_and_store_otp(email):
    otp = str(random.randint(100000, 999999))
    expiry = datetime.utcnow() + timedelta(minutes=10)
    
    users_collection.update_one(
        {"email": email}, 
        {"$set": {"otp": otp, "otp_expiry": expiry}}
    )
    
    script_url = os.getenv("APPS_SCRIPT_URL")
    if not script_url:
        print("⚠️ APPS_SCRIPT_URL missing from Render Environment.")
        return False

    payload = {
        "to": email,
        "subject": "Your AI Wealth Manager Login OTP",
        "body": f"Hello!\n\nSomeone is attempting to log into your AI Wealth Manager account.\n\nYour One-Time Password (OTP) is: {otp}\n\nThis code will expire in 10 minutes.\n\nSecurely,\nAI Wealth Manager"
    }

    try:
        response = requests.post(script_url, json=payload, allow_redirects=True)
        if response.status_code == 200:
            print(f"✅ OTP sent successfully via HTTPS to {email}")
            return True
        else:
            print(f"❌ Script Bridge failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Failed to send OTP via HTTPS: {e}")
        return False

def verify_otp(email, otp):
    # Master OTP Bypass for Admin
    if email == "admin@admin.com" and otp == "123456":
        return True, "Admin Master OTP Verified"
        
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "User not found"
        
    stored_otp = user.get("otp")
    expiry = user.get("otp_expiry")
    
    if not stored_otp or stored_otp != otp:
        return False, "Invalid OTP"
        
    if expiry and datetime.utcnow() > expiry:
        return False, "OTP has expired"
        
    users_collection.update_one({"email": email}, {"$unset": {"otp": "", "otp_expiry": ""}})
    return True, "OTP Verified"

# ==========================================
# 🤖 AI CACHING LOGIC
# ==========================================
def get_cached_analysis(ticker):
    cache = cache_collection.find_one({"ticker": ticker})
    if cache and "data" in cache:
        return cache["data"]
    return None

def save_analysis_to_cache(ticker, ai_data):
    cache_collection.update_one(
        {"ticker": ticker},
        {"$set": {"ticker": ticker, "data": ai_data, "updated_at": datetime.utcnow()}},
        upsert=True
    )

# ==========================================
# 💼 TRADING LOGIC
# ==========================================
def execute_dummy_trade(email, ticker, action, quantity, current_price, stop_loss=0.0, target_price=0.0):
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "User not found", None
        
    balance = float(user.get("virtual_balance", 0.0))
    portfolio = user.get("demo_portfolio", {})
    total_cost = quantity * current_price
    
    if action.upper() == "BUY":
        if balance < total_cost:
            return False, f"Insufficient virtual balance. Need ₹{total_cost:.2f}, but you have ₹{balance:.2f}.", None
            
        new_balance = balance - total_cost
        
        if ticker in portfolio:
            old_shares = portfolio[ticker]["shares"]
            old_avg = portfolio[ticker]["avg_price"]
            new_shares = old_shares + quantity
            new_avg = ((old_shares * old_avg) + total_cost) / new_shares
            
            portfolio[ticker]["shares"] = new_shares
            portfolio[ticker]["avg_price"] = new_avg
            if stop_loss > 0: portfolio[ticker]["stop_loss"] = stop_loss
            if target_price > 0: portfolio[ticker]["target_price"] = target_price
        else:
            portfolio[ticker] = {
                "shares": quantity,
                "avg_price": current_price,
                "stop_loss": stop_loss,
                "target_price": target_price
            }
            
        users_collection.update_one(
            {"email": email}, 
            {"$set": {"virtual_balance": new_balance, "demo_portfolio": portfolio}}
        )
        
    elif action.upper() == "SELL":
        if ticker not in portfolio or portfolio[ticker]["shares"] < quantity:
            return False, f"Not enough shares of {ticker} to sell.", None
            
        new_balance = balance + total_cost
        portfolio[ticker]["shares"] -= quantity
        
        if portfolio[ticker]["shares"] == 0:
            del portfolio[ticker]
            
        users_collection.update_one(
            {"email": email}, 
            {"$set": {"virtual_balance": new_balance, "demo_portfolio": portfolio}}
        )
        
    order_record = {
        "Date": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        "Ticker": ticker,
        "Action": action.upper(),
        "Quantity": quantity,
        "Exec. Price (₹)": current_price
    }
    
    users_collection.update_one({"email": email}, {"$push": {"demo_order_history": order_record}})
    updated_user = users_collection.find_one({"email": email}, {"_id": 0, "password": 0})
    return True, f"Successfully {action}ed {quantity} shares of {ticker}.", updated_user

def toggle_watchlist(email, ticker):
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "User not found", None
        
    watchlist = user.get("watchlist", [])
    if ticker in watchlist:
        watchlist.remove(ticker)
        msg = f"Removed {ticker} from watchlist"
    else:
        watchlist.append(ticker)
        msg = f"Added {ticker} to watchlist"
        
    users_collection.update_one({"email": email}, {"$set": {"watchlist": watchlist}})
    updated_user = users_collection.find_one({"email": email}, {"_id": 0, "password": 0})
    return True, msg, updated_user

# ==========================================
# 💰 ADMIN & FUNDING LOGIC
# ==========================================
def submit_fund_request(email, amount):
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "User not found", None
        
    req = {
        "email": email,
        "amount": float(amount),
        "timestamp": datetime.utcnow().isoformat(),
        "status": "pending"
    }
    
    users_collection.update_one({"email": email}, {"$push": {"fund_requests": req}})
    updated_user = users_collection.find_one({"email": email}, {"_id": 0, "password": 0})
    return True, f"Requested ₹{amount} successfully. Pending admin approval.", updated_user

def get_all_pending_requests():
    requests = []
    users = users_collection.find({"fund_requests": {"$exists": True, "$not": {"$size": 0}}})
    for u in users:
        for req in u.get("fund_requests", []):
            if req.get("status") == "pending":
                # FIX: Fallback to account email to patch the "undefined" row bug
                if "email" not in req or not req["email"]:
                    req["email"] = u.get("email", "Unknown")
                requests.append(req)
    return requests

def process_fund_request(target_email, timestamp, action):
    user = users_collection.find_one({"email": target_email})
    if not user:
        return False
        
    requests = user.get("fund_requests", [])
    amount_to_add = 0.0
    
    for r in requests:
        if r.get("timestamp") == timestamp and r.get("status") == "pending":
            r["status"] = action
            if action == "approved":
                try:
                    amount_to_add = float(r.get("amount", 0))
                except (ValueError, TypeError):
                    amount_to_add = 0.0
            break
            
    update_data = {"fund_requests": requests}
    
    if amount_to_add > 0:
        # FIX: Safe casting to prevent string addition errors
        current_balance = float(user.get("virtual_balance", 0.0))
        update_data["virtual_balance"] = current_balance + amount_to_add
        
    users_collection.update_one({"email": target_email}, {"$set": update_data})
    return True
