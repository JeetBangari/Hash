import os
# --- CRITICAL FIX FOR STREAMLIT + CREWAI THREADING ERROR ---
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["OTEL_SDK_DISABLED"] = "true"
# -----------------------------------------------------------
import requests
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import json
from crew import ShareMarketCrew
from dotenv import load_dotenv
import random
from datetime import datetime, timedelta
from openai import OpenAI
import time 
import auth 

# Load API Keys
load_dotenv()

# Set up the UI layout
st.set_page_config(page_title="AI Wealth Manager", layout="wide", page_icon="📈")

# ==========================================================
# --- SESSION STATE INITIALIZATION (Memory) ---
# ==========================================================
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_data' not in st.session_state:
    st.session_state.user_data = None
if 'awaiting_otp' not in st.session_state:
    st.session_state.awaiting_otp = False
if 'login_email' not in st.session_state:
    st.session_state.login_email = ""

# --- MULTI-SHARE MEMORY DICTIONARIES ---
if 'active_tickers' not in st.session_state:
    st.session_state.active_tickers = []
if 'ai_data_dict' not in st.session_state:
    st.session_state.ai_data_dict = {}
if 'base_hist_dict' not in st.session_state:
    st.session_state.base_hist_dict = {}
if 'oi_fig_dict' not in st.session_state:
    st.session_state.oi_fig_dict = {}
if 'current_live_prices' not in st.session_state:
    st.session_state.current_live_prices = {}
if 'info_dict' not in st.session_state:         
    st.session_state.info_dict = {}
if "messages" not in st.session_state:
    st.session_state.messages = [] 

if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "📖 Trading Academy"

# --- CUSTOM CSS ---
st.markdown("""
<style>
[data-testid="stMetricValue"], [data-testid="stMetricValue"] > div {
    font-size: 1.4rem !important; white-space: normal !important; word-break: break-word !important; overflow: visible !important; text-overflow: clip !important; line-height: 1.2 !important;
}
[data-testid="stMetricLabel"] { white-space: normal !important; font-size: 0.9rem !important; }
div[data-testid="stRadio"] > div { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)


# ==========================================================
# --- THE GATEKEEPER: LOGIN & SIGNUP UI ---
# ==========================================================
if not st.session_state.authenticated:
    st.title("🔐 Welcome to AI Wealth Manager")
    st.markdown("Please log in or open your unified Demat account to access the terminal.")
    st.divider()
    
    tab_login, tab_signup = st.tabs(["🔑 Login", "📝 Sign Up"])
    
    with tab_signup:
        st.subheader("Open Your Unified Trading Account")
        st.caption("Every new account comes with a ₹1,00,000 Demo balance to practice strategies risk-free.")
        with st.form("signup_form"):
            new_name = st.text_input("Full Name")
            new_email = st.text_input("Email Address")
            new_phone = st.text_input("Phone Number")
            new_password = st.text_input("Create Password", type="password", autocomplete="new-password")
            experience = st.number_input("Years of Trading Experience", min_value=0, max_value=50, value=0)
            
            submit_signup = st.form_submit_button("Open Account", type="primary")
            
            if submit_signup:
                if new_name and new_email and new_phone and new_password:
                    success, msg = auth.create_user(new_name, new_email, new_phone, new_password, experience)
                    if success:
                        st.success(msg)
                        st.info("Please switch to the Login tab to access your new account.")
                    else:
                        st.error(msg)
                else:
                    st.warning("Please fill in all fields.")

    with tab_login:
        st.subheader("Sign In to Your Account")
        if not st.session_state.awaiting_otp:
            with st.form("login_form"):
                email = st.text_input("Email Address")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                submit_login = st.form_submit_button("Verify Credentials", type="primary")
                
                if submit_login:
                    success, result = auth.verify_credentials(email, password)
                    if success:
                        st.session_state.login_email = email
                        st.session_state.user_data = result
                        test_otp = auth.generate_and_store_otp(email)
                        st.session_state.awaiting_otp = True
                        st.toast(f"📲 SMS ALERT: Check your email for your secure 6-digit OTP", icon="🔔")
                        st.rerun()
                    else:
                        st.error(result)
        else:
            st.info(f"🛡️ A 6-digit OTP has been sent to **{st.session_state.login_email}**. It expires in 2 minutes.")
            with st.form("otp_form"):
                entered_otp = st.text_input("Enter 6-Digit OTP", max_chars=6)
                submit_otp = st.form_submit_button("Secure Login", type="primary")
                
                if submit_otp:
                    success, msg = auth.verify_otp(st.session_state.login_email, entered_otp)
                    if success:
                        st.session_state.authenticated = True
                        st.session_state.awaiting_otp = False
                        st.session_state.user_data = auth.users_collection.find_one({"email": st.session_state.login_email})
                        st.rerun()
                    else:
                        st.error(msg)
            
            if st.button("Cancel / Back"):
                st.session_state.awaiting_otp = False
                st.rerun()

    st.stop() 


# ==========================================================
# --- SECURE AREA: MAIN DASHBOARD & TERMINAL ---
# ==========================================================
st.title("📈 AI Share Market & Wealth Manager")
st.markdown("Powered by Multi-Agent AI Architecture")

# --- GLOBAL MODE TOGGLE ---
st.sidebar.header("⚙️ Trading Mode")
selected_mode = st.sidebar.radio(
    "Select your environment:",
    ["🎓 DEMO (Paper Trading)", "🟢 LIVE (Real Money)"],
    index=0
)
is_demo_mode = "DEMO" in selected_mode

if is_demo_mode:
    st.warning("🎓 **DEMO MODE ACTIVE:** You are trading with virtual funds. Real market execution is disabled.")
else:
    st.success("🟢 **LIVE MODE ACTIVE:** You are using real funds. Orders placed here will execute on the live exchange.")
st.divider()

# --- SIDEBAR: USER PROFILE & CONTROLS ---
with st.sidebar:
    st.divider()
    st.header("👤 User Profile")
    st.write(f"**Name:** {st.session_state.user_data.get('name', 'User')}")
    
    demo_balance = st.session_state.user_data.get('virtual_balance', 100000.00)
    live_balance = st.session_state.user_data.get('live_balance', 0.00)
    
    if is_demo_mode:
        st.metric("Virtual Cash", f"₹{demo_balance:,.2f}")
        
        with st.expander("💸 Request Extra Demo Funds"):
            req_amount = st.number_input("Amount (₹)", min_value=1000.0, step=5000.0, value=10000.0)
            if st.button("Submit Request", use_container_width=True):
                success, msg, new_user_data = auth.submit_fund_request(st.session_state.user_data['email'], req_amount)
                if success:
                    st.session_state.user_data = new_user_data
                    st.success(msg)
    else:
        st.metric("Live Cash Margin", f"₹{live_balance:,.2f}")
    
    if st.button("Log Out", type="secondary"):
        st.session_state.authenticated = False
        st.session_state.user_data = None
        st.rerun()
        
    st.divider()
    st.header("Trade Setup")
    
    # --- MULTI-SHARE INPUT ---
    with st.form(key="trade_setup_form"):
        st.write("Compare multiple stocks side-by-side:")
        current_tickers_str = ", ".join(st.session_state.active_tickers)
        ticker_input = st.text_input("Enter Tickers (comma-separated)", current_tickers_str, placeholder="e.g., ZOMATO.NS, TCS.NS").upper()
        analyze_button = st.form_submit_button("🧠 Analyze & Track Live", type="primary")

    def fetch_heavy_background_data(ticker):
        stock = yf.Ticker(ticker)
        st.session_state.base_hist_dict[ticker] = stock.history(period="max")
        
        try:
            st.session_state.info_dict[ticker] = stock.info
        except:
            st.session_state.info_dict[ticker] = {}

        try:
            expirations = stock.options
            st.session_state.oi_fig_dict[ticker] = None
            if expirations:
                valid_expiry = None
                valid_calls = None
                valid_puts = None
                for expiry in expirations[:20]:
                    opt_chain = stock.option_chain(expiry)
                    temp_calls = opt_chain.calls
                    temp_puts = opt_chain.puts
                    if 'openInterest' in temp_calls.columns: temp_calls['openInterest'] = temp_calls['openInterest'].fillna(0)
                    if 'openInterest' in temp_puts.columns: temp_puts['openInterest'] = temp_puts['openInterest'].fillna(0)
                    has_call_oi = 'openInterest' in temp_calls.columns and temp_calls['openInterest'].sum() > 0
                    has_put_oi = 'openInterest' in temp_puts.columns and temp_puts['openInterest'].sum() > 0
                    if has_call_oi or has_put_oi:
                        valid_expiry = expiry
                        valid_calls = temp_calls[temp_calls['openInterest'] > 0] if has_call_oi else temp_calls
                        valid_puts = temp_puts[temp_puts['openInterest'] > 0] if has_put_oi else temp_puts
                        break 
                if valid_expiry:
                    fig_oi = go.Figure()
                    fig_oi.add_trace(go.Bar(x=valid_calls['strike'], y=valid_calls['openInterest'], name='Call OI (Resistance)', marker_color='#ef5350'))
                    fig_oi.add_trace(go.Bar(x=valid_puts['strike'], y=valid_puts['openInterest'], name='Put OI (Support)', marker_color='#26a69a'))
                    fig_oi.update_layout(title=f"OI Profile: {valid_expiry}", xaxis_title="Strike", yaxis_title="Contracts", barmode='group', template="plotly_white", height=300)
                    st.session_state.oi_fig_dict[ticker] = fig_oi
        except:
            st.session_state.oi_fig_dict[ticker] = None

    # ==========================================================
    # --- MULTI-SHARE CACHE ROUTING & AUTO-TAB SWITCH ---
    # ==========================================================
    if analyze_button:
        raw_tickers = [t.strip() for t in ticker_input.split(",") if t.strip()]
        
        if not raw_tickers:
            st.warning("⚠️ Please enter at least one Ticker Symbol.")
        else:
            processed_tickers = [t if "." in t else f"{t}.NS" for t in raw_tickers]
            
            if len(processed_tickers) > 3:
                st.warning("For the best side-by-side experience, a maximum of 3 stocks is recommended. Showing first 3.")
                processed_tickers = processed_tickers[:3]

            st.session_state.active_tickers = processed_tickers
            st.session_state.active_tab = "📡 Trading Terminal"
            
            for ticker in processed_tickers:
                with st.spinner(f"Fetching Market Data for {ticker}..."):
                    fetch_heavy_background_data(ticker)
                    
                cached_result = auth.get_cached_analysis(ticker)
                
                if cached_result:
                    st.session_state.ai_data_dict[ticker] = cached_result
                    st.toast(f"⚡ Loaded {ticker} instantly from AI Cache!", icon="⚡")
                else:
                    with st.spinner(f"Deploying AI Agents for {ticker} (30-60s)..."):
                        try:
                            inputs = {'ticker': ticker}
                            result = ShareMarketCrew().crew().kickoff(inputs=inputs)
                            if hasattr(result, 'pydantic') and result.pydantic: 
                                final_data = result.pydantic.model_dump()
                            else: 
                                final_data = json.loads(result.raw)
                                
                            st.session_state.ai_data_dict[ticker] = final_data
                            auth.save_analysis_to_cache(ticker, final_data)
                            st.toast(f"✅ AI Analysis complete for {ticker}!")
                        except Exception as e:
                            st.error(f"An error occurred analyzing {ticker}: {e}")

# ==========================================================
# --- LIVE NEWS ---
# ==========================================================
st.write("---") 
news_query = st.text_input("🔍 Search Market News", placeholder="e.g., Reliance, Tata Motors")
@st.fragment(run_every=30)
def render_live_news():
    try:
        news_api_key = os.getenv("NEWS_API_KEY")
        if not news_api_key: return st.error("⚠️ API Key Error: Streamlit cannot find NEWS_API_KEY.")
        if news_query.strip():
            search_term = news_query.strip()
            aliases = {"reliance": "Reliance Industries", "sbi": "State Bank of India", "tcs": "Tata Consultancy Services", "infy": "Infosys"}
            if search_term.lower() in aliases: search_term = aliases[search_term.lower()]
            url = "https://newsapi.org/v2/everything"
            params = {"qInTitle": f'"{search_term}"', "language": "en", "sortBy": "publishedAt", "apiKey": news_api_key}
            box_title = f"🔴 LATEST NEWS: {search_term.upper()}"
        else:
            url = "https://newsapi.org/v2/top-headlines"
            params = {"category": "business", "language": "en", "apiKey": news_api_key}
            box_title = "🔴 LIVE MARKET ALERTS"

        response = requests.get(url, params=params)
        news_data = response.json()
        if news_data.get("status") == "ok":
            articles = news_data.get("articles", [])
            valid_articles = [a for a in articles if a.get('title') and '[Removed]' not in a.get('title')]
            if not valid_articles: return st.info(f"No recent news found for '{search_term}'.")
            display_articles = valid_articles[:5] if news_query.strip() else (random.sample(valid_articles, 5) if len(valid_articles) > 5 else valid_articles)
            redbox_html = f"""<div style="background-color: #2b0a0a; border: 1px solid #ff4b4b; border-left: 6px solid #ff0000; padding: 10px; border-radius: 5px; margin-bottom: 15px;"><h5 style="color: #ff4b4b; margin-top: 0px; margin-bottom: 10px;">{box_title}</h5>"""
            for item in display_articles:
                title, source, link = item.get('title', 'No Title'), item.get('source', {}).get('name', 'Unknown'), item.get('url', '#')
                redbox_html += f"<div style='color: #ffffff; font-size: 0.85rem; margin-bottom: 10px; line-height: 1.3;'><b>• <a href='{link}' target='_blank' style='color: #ffffff; text-decoration: none;'>{title.split(' - ')[0]}</a></b><br><span style='color: #aaaaaa; font-size: 0.75rem;'>{source}</span></div>"
            st.markdown(redbox_html + "</div>", unsafe_allow_html=True)
        else: st.error(f"NewsAPI Error: {news_data.get('message', 'Unknown Error')}")
    except: st.warning("Could not connect to news feed.")
render_live_news()


# ==========================================================
# --- DYNAMIC TAB LAYOUT (NOW PROGRAMMATIC RADIO MENU) ---
# ==========================================================
is_admin = st.session_state.user_data.get("role") == "admin"

tab_list = [
    "📖 Trading Academy", 
    "⭐ Watchlist", 
    "📡 Trading Terminal", 
    "💼 My Portfolio", 
    "💬 AI Market Assistant"
]

if is_admin:
    tab_list.append("🛡️ Admin Panel")

selected_tab = st.radio("Main Navigation", tab_list, horizontal=True, label_visibility="collapsed", key="active_tab")
st.write("---")

if selected_tab == "📖 Trading Academy":
    st.header("Welcome to the Trading Academy 🎓")
    st.markdown("""
    Whether you are preparing to make your first trade or brushing up on strategies, review these basics before hitting the live market.
    
    ### 1. What is a Stock?
    When you buy a share, you buy partial ownership of a company.
    
    ### 2. Bull vs. Bear Markets
    * 🐂 **Bull Market:** Prices are going up.
    * 🐻 **Bear Market:** Prices are falling down.
    
    ### 3. Risk Management
    Diversify your portfolio and use **Stop Losses** to automatically sell a stock if it drops too low.
    """)

elif selected_tab == "⭐ Watchlist":
    st.header("⭐ My Watchlist")
    
    current_watchlist = st.session_state.user_data.get("watchlist", [])
    
    if not current_watchlist:
        st.info("Your watchlist is currently empty. Go to the Trading Terminal to search for a stock and add it here!")
    else:
        st.write("Tracking live prices for your favorite stocks:")
        
        watchlist_data = []
        with st.spinner("Fetching live market data..."):
            for t in current_watchlist:
                try:
                    stock_ticker = yf.Ticker(t)
                    live_p = round(stock_ticker.fast_info.last_price, 2)
                    prev_close = round(stock_ticker.fast_info.previous_close, 2)
                    
                    change = live_p - prev_close
                    pct_change = (change / prev_close) * 100
                    
                    watchlist_data.append({
                        "Ticker": t,
                        "Live Price": f"₹{live_p:,.2f}",
                        "Day Change": f"{'+' if change > 0 else ''}₹{change:,.2f} ({pct_change:,.2f}%)"
                    })
                except:
                    watchlist_data.append({"Ticker": t, "Live Price": "Data Unavailable", "Day Change": "-"})
                    
        df_wl = pd.DataFrame(watchlist_data)
        st.dataframe(df_wl, use_container_width=True, hide_index=True)


elif selected_tab == "📡 Trading Terminal":
    if not st.session_state.active_tickers:
        st.info("👈 Please enter Stock Ticker Symbol(s) in the left sidebar and click 'Analyze & Track Live' to start your terminal. (You can enter multiple separated by commas!)")
    else:
        @st.fragment(run_every=60)
        def render_live_price_charts():
            tickers = st.session_state.active_tickers
            cols = st.columns(len(tickers))
            
            for i, ticker in enumerate(tickers):
                with cols[i]:
                    with st.container(border=True):
                        # Top Header & Watchlist Toggle
                        header_col, btn_col = st.columns([3, 1])
                        header_col.subheader(ticker)
                        
                        current_wl = st.session_state.user_data.get("watchlist", [])
                        in_wl = ticker in current_wl
                        if btn_col.button("🌟" if in_wl else "⭐", key=f"wl_{ticker}", help="Toggle Watchlist"):
                            success, msg, new_user_data = auth.toggle_watchlist(st.session_state.user_data['email'], ticker)
                            if success:
                                st.session_state.user_data = new_user_data
                                st.toast(msg)
                                st.rerun()

                        # Logic and Variables
                        ai_data = st.session_state.ai_data_dict.get(ticker)
                        hist = st.session_state.base_hist_dict.get(ticker)
                        info = st.session_state.info_dict.get(ticker, {}) 
                        
                        if hist is None or hist.empty: 
                            st.warning("Market data unavailable.")
                            continue

                        stock = yf.Ticker(ticker)
                        try:
                            current_price = round(stock.fast_info.last_price, 2)
                            hist.iloc[-1, hist.columns.get_loc('Close')] = current_price
                            if current_price > hist.iloc[-1]['High']: hist.iloc[-1, hist.columns.get_loc('High')] = current_price
                            if current_price < hist.iloc[-1]['Low']: hist.iloc[-1, hist.columns.get_loc('Low')] = current_price
                        except:
                            current_price = round(hist['Close'].iloc[-1], 2)
                            
                        st.session_state.current_live_prices[ticker] = current_price
                        currency = "₹" if ticker.endswith((".NS", ".BO")) else "$"

                        # Metrics
                        st.metric("Live Price", f"{currency}{current_price}")
                        m1, m2 = st.columns(2)
                        if ai_data:
                            m1.metric("AI Target", f"{currency}{ai_data.get('target_price', 0)}")
                            m2.metric("Stop Loss", f"{currency}{ai_data.get('stop_loss', 0)}")
                            st.write(f"**AI Decision:** {ai_data.get('decision', 'N/A')}")
                        else:
                            st.write("**AI Decision:** Awaiting...")

                        # Chart
                        end_date = hist.index[-1]
                        start_date = end_date - timedelta(days=30)
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="Live Price", increasing_line_color='#26a69a', decreasing_line_color='#ef5350'))
                        if ai_data:
                            fig.add_hline(y=ai_data.get('target_price', 0), line_dash="dash", line_color="#26a69a", annotation_text="Target")
                            fig.add_hline(y=ai_data.get('stop_loss', 0), line_dash="dash", line_color="#ef5350", annotation_text="Stop Loss")
                        
                        xaxis_layout = dict(type="date", rangebreaks=[dict(bounds=["sat", "mon"])], tickmode="auto", nticks=10, showgrid=True, gridcolor='#E6E6E6')
                        xaxis_layout['range'] = [start_date, end_date]
                        fig.update_layout(uirevision=ticker, hovermode="x unified", xaxis=xaxis_layout, yaxis=dict(showgrid=True, gridcolor='#E6E6E6'), xaxis_rangeslider_visible=False, template="plotly_white", height=300, margin=dict(l=5, r=5, t=10, b=10))
                        st.plotly_chart(fig, use_container_width=True, key=f"chart_{ticker}")

                        # Expanders for AI, Fundamentals & OI
                        with st.expander("🏢 Fundamentals & Key Metrics"):
                            if info:
                                mc = info.get('marketCap', 0)
                                if mc >= 1e12: mc_str = f"₹{mc/1e12:.2f}T"
                                elif mc >= 1e9: mc_str = f"₹{mc/1e9:.2f}B"
                                else: mc_str = f"₹{mc:,.0f}"
                                
                                st.write(f"**Market Cap:** {mc_str}")
                                st.write(f"**Trailing P/E:** {info.get('trailingPE', 'N/A')}")
                                st.write(f"**Forward P/E:** {info.get('forwardPE', 'N/A')}")
                                st.write(f"**52-Week High:** {currency}{info.get('fiftyTwoWeekHigh', 'N/A')}")
                                st.write(f"**52-Week Low:** {currency}{info.get('fiftyTwoWeekLow', 'N/A')}")
                                st.write(f"**Sector:** {info.get('sector', 'N/A')}")
                            else:
                                st.write("Fundamental data currently unavailable.")

                        with st.expander("🧠 Deep AI Reasoning"):
                            if ai_data:
                                st.write("**Tech:**", ai_data.get("technical_reasoning"))
                                st.write("**Fund:**", ai_data.get("fundamental_reasoning"))
                            else: st.write("Loading...")
                                
                        with st.expander("📊 Options Chain (OI)"):
                            oi_fig = st.session_state.oi_fig_dict.get(ticker)
                            if oi_fig: st.plotly_chart(oi_fig, use_container_width=True, key=f"oi_{ticker}")
                            else: st.write("OI data unavailable.")

        render_live_price_charts()
        
        # ==========================================================
        # --- UNIVERSAL EXECUTION DESK (WITH RISK MANAGEMENT) ---
        # ==========================================================
        st.write("---")
        
        if is_demo_mode:
            st.subheader("🏦 Paper Trading Execution Desk")
        else:
            st.subheader("🔴 LIVE Execution Desk")
        
        trade_ticker = st.selectbox("Select Asset to Trade", st.session_state.active_tickers)
        
        if is_demo_mode:
            portfolio_key = "demo_portfolio" if "demo_portfolio" in st.session_state.user_data else "portfolio"
            owned_shares = st.session_state.user_data.get(portfolio_key, {}).get(trade_ticker, {}).get("shares", 0)
            st.write(f"**Virtual Balance:** ₹{demo_balance:,.2f} | **Currently Owned:** {owned_shares} shares of {trade_ticker}")
        else:
            owned_shares = st.session_state.user_data.get("live_portfolio", {}).get(trade_ticker, {}).get("shares", 0)
            st.write(f"**Live Margin:** ₹{live_balance:,.2f} | **Currently Owned:** {owned_shares} shares of {trade_ticker}")
            
        # FIX: Replaced st.form with st.container so the Estimated Value updates live!
        with st.container(border=True):
            col1, col2, col3 = st.columns([1, 1, 1])
            trade_action = col1.selectbox("Action", ["BUY", "SELL"])
            trade_qty = col2.number_input("Quantity", min_value=1, step=1, value=1)
            
            current_trade_price = st.session_state.current_live_prices.get(trade_ticker, 0.0)
            estimated_total = trade_qty * current_trade_price
            col3.metric("Estimated Total Value", f"₹{estimated_total:,.2f}")
            
            st.markdown("**Risk Management (Optional)**")
            sl_col, tp_col, btn_col = st.columns([1, 1, 1])
            
            trade_sl = sl_col.number_input("Stop Loss Limit (₹)", min_value=0.0, step=0.5, value=0.0, help="Automatically sell if price drops to this level.")
            trade_tp = tp_col.number_input("Target Price Limit (₹)", min_value=0.0, step=0.5, value=0.0, help="Automatically sell if price reaches this level.")
            
            btn_col.markdown("<br>", unsafe_allow_html=True)
            btn_type = "secondary" if is_demo_mode else "primary"
            btn_label = "Execute Demo Order" if is_demo_mode else "EXECUTE LIVE ORDER"
            
            # Form submit button changed to a standard button
            submit_trade = btn_col.button(btn_label, type=btn_type, use_container_width=True)
            
            if submit_trade:
                if current_trade_price == 0.0:
                    st.error("Market price is loading. Please wait a moment and try again.")
                else:
                    if is_demo_mode:
                        success, msg, new_user_data = auth.execute_dummy_trade(
                            email=st.session_state.user_data['email'],
                            ticker=trade_ticker,
                            action=trade_action,
                            quantity=trade_qty,
                            current_price=current_trade_price,
                            stop_loss=trade_sl,
                            target_price=trade_tp
                        )
                    else:
                        success, msg = False, "Live trading API is currently disconnected. Switch to Demo Mode to test strategies."
                        new_user_data = st.session_state.user_data
                        
                    if success:
                        st.session_state.user_data = new_user_data
                        st.success(msg)
                        time.sleep(1.5)
                        st.rerun() 
                    else:
                        st.error(msg)

elif selected_tab == "💼 My Portfolio":
    st.header(f"💼 {'Demo' if is_demo_mode else 'Live'} Portfolio Holdings")
    
    if is_demo_mode:
        portfolio_key = "demo_portfolio" if "demo_portfolio" in st.session_state.user_data else "portfolio"
        portfolio = st.session_state.user_data.get(portfolio_key, {})
    else:
        portfolio = st.session_state.user_data.get("live_portfolio", {})
        
    active_holdings = {k: v for k, v in portfolio.items() if isinstance(v, dict) and v.get("shares", 0) > 0}
    
    if not active_holdings:
        st.info(f"You currently do not have any active stock holdings in your {'Demo' if is_demo_mode else 'Live'} account.")
    else:
        with st.spinner("Fetching live market prices for your portfolio..."):
            portfolio_rows = []
            total_invested = 0.0
            total_current_val = 0.0
            
            for ticker, details in active_holdings.items():
                shares = details.get("shares", 0)
                avg_buy_price = details.get("avg_price", 0.0) 
                sl_price = details.get("stop_loss", 0.0)
                tp_price = details.get("target_price", 0.0)
                
                try: live_price = round(yf.Ticker(ticker).fast_info.last_price, 2)
                except: live_price = avg_buy_price 
                    
                invested_value = shares * avg_buy_price
                current_value = shares * live_price
                pnl = current_value - invested_value
                
                total_invested += invested_value
                total_current_val += current_value
                
                sl_display = f"₹{sl_price:,.2f}" if sl_price > 0 else "None"
                tp_display = f"₹{tp_price:,.2f}" if tp_price > 0 else "None"
                
                portfolio_rows.append({
                    "Ticker": ticker, 
                    "Shares": shares, 
                    "Avg Price": f"₹{avg_buy_price:,.2f}", 
                    "Live Price": f"₹{live_price:,.2f}", 
                    "Stop Loss": sl_display,
                    "Target": tp_display,
                    "Invested": f"₹{invested_value:,.2f}", 
                    "Current Value": f"₹{current_value:,.2f}", 
                    "P&L": f"{'+' if pnl >= 0 else ''}₹{pnl:,.2f}"
                })
            
            total_pnl = total_current_val - total_invested
            st.markdown("### Portfolio Summary")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Invested", f"₹{total_invested:,.2f}")
            col2.metric("Current Portfolio Value", f"₹{total_current_val:,.2f}", delta=f"₹{total_pnl:,.2f}")
            
            if is_demo_mode: col3.metric("Available Virtual Cash", f"₹{demo_balance:,.2f}")
            else: col3.metric("Available Cash Margin", f"₹{live_balance:,.2f}")
            
            st.divider()
            st.markdown("### Current Holdings & Risk Limits")
            st.dataframe(pd.DataFrame(portfolio_rows), use_container_width=True, hide_index=True)
            
    history_key = "demo_order_history" if is_demo_mode else "live_order_history"
    if history_key not in st.session_state.user_data and "order_history" in st.session_state.user_data:
        history_key = "order_history" 
        
    order_history = st.session_state.user_data.get(history_key, [])
    if order_history:
        st.write("")
        with st.expander(f"📜 View { 'Demo' if is_demo_mode else 'Live' } Orders History"):
            st.dataframe(pd.DataFrame(order_history).iloc[::-1], use_container_width=True, hide_index=True)

elif selected_tab == "💬 AI Market Assistant":
    user = st.session_state.user_data
    u_name = user.get('name', 'User')
    u_exp = user.get('experience_years', 0)
    u_demo_port = user.get('demo_portfolio', {})
    u_live_port = user.get('live_portfolio', {})
    u_demo_trades = user.get('demo_order_history', [])[-5:]
    u_live_trades = user.get('live_order_history', [])[-5:]
    u_analyzed = st.session_state.active_tickers
    
    dynamic_system_prompt = f"""
    You are an elite AI Wealth Manager assigned to your client, {u_name}.
    
    CLIENT CONTEXT:
    - Trading Experience: {u_exp} years. Adjust your terminology to match their level.
    - Stocks currently analyzing on screen: {u_analyzed}
    - Demo Account Holdings: {u_demo_port}
    - Live Account Holdings: {u_live_port}
    - Recent Demo Trades: {u_demo_trades}
    - Recent Live Trades: {u_live_trades}
    
    DIRECTIVES:
    1. Analyze their 'Trades' and 'Holdings' to determine their trading style.
    2. Give hyper-personalized advice based on what they actually own or are analyzing right now. 
    3. ALWAYS use the 'get_live_stock_price' tool when mentioning specific stocks to provide accurate data.
    4. Act like a human advisor who knows their account intimately. Do not roboticly list out the data above.
    """
    
    if not st.session_state.messages:
        st.session_state.messages = [{"role": "system", "content": dynamic_system_prompt}]
    elif st.session_state.messages[0]["role"] == "system":
        st.session_state.messages[0]["content"] = dynamic_system_prompt 
        
    col_chat_title, col_chat_clear = st.columns([4, 1])
    with col_chat_title: st.subheader("💬 Ask Your Personalized AI Wealth Manager")
    with col_chat_clear:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = [{"role": "system", "content": dynamic_system_prompt}]
            st.rerun()

    def get_live_stock_price(ticker):
        try: return f"₹{round(yf.Ticker(ticker).fast_info.last_price, 2)}"
        except: return "Price currently unavailable"
        
    tools = [{"type": "function", "function": {"name": "get_live_stock_price", "description": "Get current price.", "parameters": {"type": "object", "properties": {"ticker": {"type": "string", "description": "Ticker symbol."}}, "required": ["ticker"]}}}]

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key: st.warning("⚠️ Please add your OPENAI_API_KEY to your .env file.")
    else:
        client = OpenAI(api_key=openai_api_key)
        chat_container = st.container()
        
        with chat_container:
            for msg in st.session_state.messages:
                if msg["role"] not in ["system", "tool"] and msg.get("content"):
                    with st.chat_message(msg["role"]): st.markdown(msg["content"])
                    
        if prompt := st.chat_input("Ask a question about your portfolio or the market..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with chat_container:
                with st.chat_message("user"): st.markdown(prompt)
                with st.chat_message("assistant"):
                    msg_placeholder = st.empty()
                    try:
                        with st.spinner("Analyzing your portfolio..."):
                            resp = client.chat.completions.create(model="gpt-4o-mini", messages=st.session_state.messages, tools=tools, tool_choice="auto")
                        resp_msg = resp.choices[0].message
                        
                        if resp_msg.tool_calls:
                            st.session_state.messages.append(resp_msg.model_dump(exclude_unset=True))
                            for call in resp_msg.tool_calls:
                                args = json.loads(call.function.arguments)
                                price = get_live_stock_price(args.get("ticker"))
                                st.session_state.messages.append({"tool_call_id": call.id, "role": "tool", "name": "get_live_stock_price", "content": str(price)})
                                
                            stream = client.chat.completions.create(model="gpt-4o-mini", messages=st.session_state.messages, stream=True)
                            full_resp = ""
                            for chunk in stream:
                                if chunk.choices[0].delta.content:
                                    full_resp += chunk.choices[0].delta.content
                                    msg_placeholder.markdown(full_resp + "▌")
                            msg_placeholder.markdown(full_resp)
                            st.session_state.messages.append({"role": "assistant", "content": full_resp})
                        else:
                            full_resp = resp_msg.content
                            disp_text = ""
                            for word in full_resp.split(" "):
                                disp_text += word + " "
                                msg_placeholder.markdown(disp_text + "▌")
                                time.sleep(0.04)
                            msg_placeholder.markdown(full_resp)
                            st.session_state.messages.append({"role": "assistant", "content": full_resp})
                    except Exception as e: msg_placeholder.error(f"Error: {e}")
            st.rerun()

elif is_admin and selected_tab == "🛡️ Admin Panel":
    st.header("🛡️ Company Admin Dashboard")
    st.markdown("Manage user fund requests and platform activity here.")
    
    st.subheader("Pending Demo Fund Requests")
    pending_requests = auth.get_all_pending_requests()
    
    if not pending_requests:
        st.info("✅ All caught up! No pending fund requests at the moment.")
    else:
        for req in pending_requests:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                col1.write(f"**User:** {req['name']} ({req['email']})")
                col2.write(f"**Requested:** ₹{req['amount']:,.2f}")
                
                if col3.button("✅ Approve", key=f"app_{req['timestamp']}", type="primary"):
                    auth.process_fund_request(req['email'], req['timestamp'], "approved")
                    st.success(f"Approved ₹{req['amount']} for {req['name']}!")
                    time.sleep(1)
                    st.rerun()
                    
                if col4.button("❌ Reject", key=f"rej_{req['timestamp']}"):
                    auth.process_fund_request(req['email'], req['timestamp'], "rejected")
                    st.error("Request Rejected.")
                    time.sleep(1)
                    st.rerun()