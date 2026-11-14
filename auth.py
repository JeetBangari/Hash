import os
import random
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pymongo import MongoClient
import bcrypt
from dotenv import load_dotenv

# Load environment variables (useful for local testing)
load_dotenv()

# ==========================================
# 🗄️ DATABASE CONNECTION
# ==========================================
# Grabs the connection string from Render Environment Variables
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)

# Automatically selects "WealthManager" because it is in your MONGO_URI string
db = client.get_default_database()

users_collection = db["users"]
cache_collection = db["ai_analysis_cache"]

# ==========================================
# 🔐 AUTHENTICATION & OTP LOGIC
# ==========================================
def verify_credentials(email, password):
    """Verifies user login credentials."""
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "User not found. Please create an account."
    
    # Check hashed password
    if bcrypt.checkpw(password.encode('utf-8'), user['password']):
        return True, "Valid credentials"
    
    return False, "Invalid password"

def generate_and_store_otp(email):
    """Generates a 6-digit OTP, stores it in MongoDB, and sends it via Email."""
    otp = str(random.randint(100000, 999999))
    expiry = datetime.utcnow() + timedelta(minutes=10)
    
    # Store OTP in the database
    users_collection.update_one(
        {"email": email}, 
        {"$set": {"otp": otp, "otp_expiry": expiry}}
    )
    
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    
    if not sender_email or not sender_password:
        print("⚠️ SENDER_EMAIL or SENDER_PASSWORD missing from Render Environment.")
        return False

    try:
        # Construct the email
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = email
        msg['Subject'] = "Your AI Wealth Manager Login OTP"
        
        body = f"Hello!\n\nSomeone is attempting to log into your AI Wealth Manager account.\n\nYour One-Time Password (OTP) is: {otp}\n\nThis code will expire in 10 minutes.\n\nSecurely,\nAI Wealth Manager"
        msg.attach(MIMEText(body, 'plain'))
        
        # 🟢 FIXED: Use Port 587 and STARTTLS to bypass Render's Port 465 firewall block
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo()
        server.starttls() # Secure the connection
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ OTP sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send OTP email: {e}")
        return False

def verify_otp(email, otp):
    """Verifies the OTP provided by the user."""
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "User not found"
        
    stored_otp = user.get("otp")
    expiry = user.get("otp_expiry")
    
    if not stored_otp or stored_otp != otp:
        return False, "Invalid OTP"
        
    if expiry and datetime.utcnow() > expiry:
        return False, "OTP has expired"
        
    # Clear the OTP from the database after a successful login for security
    users_collection.update_one({"email": email}, {"$unset": {"otp": "", "otp_expiry": ""}})
    return True, "OTP Verified"

# ==========================================
# 🤖 AI CACHING LOGIC
# ==========================================
def get_cached_analysis(ticker):
    """Retrieves AI analysis from MongoDB cache if available."""
    cache = cache_collection.find_one({"ticker": ticker})
    if cache and "data" in cache:
        return cache["data"]
    return None

def save_analysis_to_cache(ticker, ai_data):
    """Saves fresh AI analysis to MongoDB cache."""
    cache_collection.update_one(
        {"ticker": ticker},
        {"$set": {"ticker": ticker, "data": ai_data, "updated_at": datetime.utcnow()}},
        upsert=True
    )

# ==========================================
# 💼 TRADING & PORTFOLIO LOGIC
# ==========================================
def execute_dummy_trade(email, ticker, action, quantity, current_price, stop_loss=0.0, target_price=0.0):
    """Executes a paper trade and updates the user's virtual portfolio and balance."""
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "User not found", None
        
    balance = user.get("virtual_balance", 0.0)
    portfolio = user.get("demo_portfolio", {})
    
    total_cost = quantity * current_price
    
    if action.upper() == "BUY":
        if balance < total_cost:
            return False, f"Insufficient virtual balance. Need ₹{total_cost:.2f}, but you have ₹{balance:.2f}.", None
            
        new_balance = balance - total_cost
        
        # Update existing holding or create new one
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
        
    # Append to Order History
    order_record = {
        "Date": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        "Ticker": ticker,
        "Action": action.upper(),
        "Quantity": quantity,
        "Exec. Price (₹)": current_price
    }
    
    users_collection.update_one({"email": email}, {"$push": {"demo_order_history": order_record}})
    
    # Return updated user profile
    updated_user = users_collection.find_one({"email": email}, {"_id": 0, "password": 0})
    return True, f"Successfully {action}ed {quantity} shares of {ticker}.", updated_user

def toggle_watchlist(email, ticker):
    """Adds or removes a ticker from the user's watchlist."""
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
    """Submits a request to the admin to add virtual funds."""
    user = users_collection.find_one({"email": email})
    if not user:
        return False, "User not found", None
        
    req = {
        "email": email,
        "amount": amount,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "pending"
    }
    
    users_collection.update_one({"email": email}, {"$push": {"fund_requests": req}})
    updated_user = users_collection.find_one({"email": email}, {"_id": 0, "password": 0})
    return True, f"Requested ₹{amount} successfully. Pending admin approval.", updated_user

def get_all_pending_requests():
    """Fetches all pending fund requests across all users for the Admin panel."""
    requests = []
    users = users_collection.find({"fund_requests": {"$exists": True, "$not": {"$size": 0}}})
    for u in users:
        for req in u.get("fund_requests", []):
            if req.get("status") == "pending":
                requests.append(req)
    return requests

def process_fund_request(target_email, timestamp, action):
    """Admin function to approve or reject a user's fund request."""
    user = users_collection.find_one({"email": target_email})
    if not user:
        return False
        
    requests = user.get("fund_requests", [])
    amount_to_add = 0
    
    for r in requests:
        if r.get("timestamp") == timestamp and r.get("status") == "pending":
            r["status"] = action
            if action == "approved":
                amount_to_add = r.get("amount", 0)
            break
            
    update_data = {"fund_requests": requests}
    
    if amount_to_add > 0:
        update_data["virtual_balance"] = user.get("virtual_balance", 0.0) + amount_to_add
        
    users_collection.update_one({"email": target_email}, {"$set": update_data})
    return True
