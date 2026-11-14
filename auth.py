import os
import bcrypt
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB Atlas
client = MongoClient(os.getenv("MONGO_URI"))
db = client['WealthManager']
users_collection = db['users']

def create_user(name, email, phone, password, experience_years):
    if users_collection.find_one({"email": email}):
        return False, "An account with this email address already exists."

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    user_doc = {
        "name": name,
        "email": email,
        "phone": phone,
        "password": hashed_password,
        "experience_years": experience_years,
        "created_at": datetime.now(),
        
        "virtual_balance": 100000.00,  
        "live_balance": 0.00,          
        
        "demo_portfolio": {},
        "live_portfolio": {},
        
        "demo_order_history": [],
        "live_order_history": [],
        
        "watchlist": [],
        
        "role": "admin" if email == "admin@admin.com" else "user",
        "fund_requests": []
    }
    
    users_collection.insert_one(user_doc)
    return True, "Account created successfully! You received ₹1,00,000 Demo Cash to practice."

def verify_credentials(email, password):
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "Email not found."
    
    # ==========================================================
    # --- ADDED: ADMIN MASTER PASSWORD OVERRIDE ---
    # ==========================================================
    if email == "admin@admin.com" and password == "admin123":
        return True, user
    # ==========================================================
    
    if bcrypt.checkpw(password.encode('utf-8'), user['password']):
        return True, user
    return False, "Incorrect password."

def send_real_email(receiver_email, otp):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    
    if not sender_email or not sender_password:
        print("Error: Email credentials missing from .env file")
        return False
        
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "🔒 Your AI Wealth Manager Login OTP"
    
    body = f"""Hello!\n\nSomeone is trying to log into your AI Wealth Manager account.\nYour 6-digit secure OTP is: {otp}\n\nThis code will expire in exactly 2 minutes.\n\nHappy Trading!"""

    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def generate_and_store_otp(email):
    if email == "admin@admin.com":
        otp = "123456" 
    else:
        otp = str(random.randint(100000, 999999))
        
    expiry = datetime.now() + timedelta(minutes=2) 
    
    users_collection.update_one(
        {"email": email}, 
        {"$set": {"current_otp": otp, "otp_expiry": expiry}}
    )
    
    if email != "admin@admin.com":
        send_real_email(email, otp)
        
    return otp

def verify_otp(email, entered_otp):
    user = users_collection.find_one({"email": email})
    if not user or "current_otp" not in user:
        return False, "Invalid session."
    
    if datetime.now() > user['otp_expiry']:
        return False, "OTP has expired. Please request a new one."
        
    if entered_otp == user['current_otp']:
        users_collection.update_one({"email": email}, {"$unset": {"current_otp": "", "otp_expiry": ""}})
        return True, "Login successful!"
        
    return False, "Incorrect OTP."

# ==========================================================
# --- UPDATED: ENGINE WITH STOP LOSS & TARGET PRICE ---
# ==========================================================
def execute_dummy_trade(email, ticker, action, quantity, current_price, stop_loss=0.0, target_price=0.0):
    user = users_collection.find_one({"email": email})
    if not user: 
        return False, "User not found", None

    balance = user.get("virtual_balance", 0.0)
    portfolio = user.get("demo_portfolio", {})
    history = user.get("demo_order_history", [])

    # Calculate total transaction value
    total_value = quantity * current_price

    if action == "BUY":
        if balance < total_value:
            return False, f"Insufficient funds. You need ₹{total_value:,.2f}", None

        # 1. Deduct money for BUY
        users_collection.update_one({"email": email}, {"$inc": {"virtual_balance": -total_value}})

        # 2. Add shares to portfolio
        if ticker in portfolio:
            old_shares = portfolio[ticker].get("shares", 0)
            old_avg = portfolio[ticker].get("avg_price", 0.0)
            new_shares = old_shares + quantity
            new_avg = ((old_shares * old_avg) + total_value) / new_shares
            
            portfolio[ticker]["shares"] = new_shares
            portfolio[ticker]["avg_price"] = new_avg
            portfolio[ticker]["stop_loss"] = stop_loss
            portfolio[ticker]["target_price"] = target_price
        else:
            portfolio[ticker] = {
                "shares": quantity, 
                "avg_price": current_price,
                "stop_loss": stop_loss,
                "target_price": target_price
            }

    elif action == "SELL":
        if ticker not in portfolio or portfolio[ticker].get("shares", 0) < quantity:
            return False, f"You do not own enough shares of {ticker} to sell.", None

        # 1. ADD MONEY BACK FOR SELL (This was the missing line causing your bug!)
        users_collection.update_one({"email": email}, {"$inc": {"virtual_balance": total_value}})

        # 2. Remove shares from portfolio
        portfolio[ticker]["shares"] -= quantity
        
        # If shares hit 0, completely remove the stock from the portfolio
        if portfolio[ticker]["shares"] <= 0:
            del portfolio[ticker]

    # Record the transaction in the history ledger
    from datetime import datetime
    history.append({
        "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Ticker": ticker,
        "Action": action,
        "Quantity": quantity,
        "Exec. Price (₹)": current_price
    })

    # Save the updated portfolio and history back to MongoDB
    users_collection.update_one(
        {"email": email},
        {"$set": {
            "demo_portfolio": portfolio, 
            "demo_order_history": history
        }}
    )

    # Fetch and return the freshly updated user data so the frontend UI updates instantly
    updated_user = users_collection.find_one({"email": email}, {"_id": 0, "password": 0})
    return True, f"Successfully executed {action} order for {quantity} shares of {ticker}.", updated_user

def toggle_watchlist(email, ticker):
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "User not found.", None
    
    watchlist = user.get("watchlist", [])
    
    if ticker in watchlist:
        watchlist.remove(ticker)
        msg = f"Removed {ticker} from Watchlist."
    else:
        watchlist.append(ticker)
        msg = f"⭐ Added {ticker} to Watchlist."
        
    users_collection.update_one(
        {"email": email},
        {"$set": {"watchlist": watchlist}}
    )
    
    updated_user = users_collection.find_one({"email": email})
    return True, msg, updated_user


def submit_fund_request(email, amount):
    request_doc = {
        "amount": float(amount),
        "status": "pending",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    users_collection.update_one(
        {"email": email},
        {"$push": {"fund_requests": request_doc}}
    )
    updated_user = users_collection.find_one({"email": email})
    return True, f"Request for ₹{amount:,.2f} submitted to the admin.", updated_user

def get_all_pending_requests():
    users = users_collection.find({"fund_requests.status": "pending"})
    all_requests = []
    
    for u in users:
        for req in u.get("fund_requests", []):
            if req["status"] == "pending":
                all_requests.append({
                    "email": u["email"],
                    "name": u.get("name", "Unknown"),
                    "amount": req["amount"],
                    "timestamp": req["timestamp"]
                })
    return all_requests

def process_fund_request(email, timestamp, action):
    user = users_collection.find_one({"email": email})
    if not user: return False

    requests = user.get("fund_requests", [])
    amount_to_add = 0
    
    for req in requests:
        if req["timestamp"] == timestamp and req["status"] == "pending":
            req["status"] = action
            amount_to_add = req["amount"]
            break

    update_query = {"$set": {"fund_requests": requests}}

    if action == "approved":
        new_balance = user.get("virtual_balance", 0.0) + amount_to_add
        update_query["$set"]["virtual_balance"] = new_balance

    users_collection.update_one({"email": email}, update_query)
    return True

# ==========================================================
# --- SPEED UPGRADE (CACHE ENGINE) ---
# ==========================================================
def get_cached_analysis(ticker):
    cache_collection = db['ai_analysis_cache']
    four_hours_ago = datetime.now() - timedelta(hours=4)
    
    cached_data = cache_collection.find_one({
        "ticker": ticker,
        "timestamp": {"$gte": four_hours_ago}
    })
    
    if cached_data:
        return cached_data.get("ai_data")
    return None

def save_analysis_to_cache(ticker, ai_data):
    cache_collection = db['ai_analysis_cache']
    cache_collection.update_one(
        {"ticker": ticker},
        {"$set": {
            "ticker": ticker,
            "ai_data": ai_data,
            "timestamp": datetime.now()
        }},
        upsert=True 
    )