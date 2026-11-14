import yfinance as yf
import pandas as pd
import os
import time

def fetch_entire_market(ticker_list, years=5):
    # Create a dedicated folder for the whole market
    folder_name = 'market_data_5Y'
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
        
    print(f"🚀 Starting bulk download for {len(ticker_list)} stocks...")
    
    successful = 0
    failed = []

    for ticker in ticker_list:
        file_path = f"{folder_name}/{ticker}_historical.csv"
        
        # Skip if we already downloaded it (useful if the script crashes and you restart)
        if os.path.exists(file_path):
            print(f"⏭️ Skipping {ticker} (Already downloaded)")
            continue
            
        print(f"📡 Fetching {ticker}...")
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=f"{years}y", interval="1d")
            
            if not df.empty:
                # Clean the data
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                df.index = df.index.strftime('%Y-%m-%d')
                
                # Save to CSV
                df.to_csv(file_path)
                successful += 1
            else:
                failed.append(ticker)
                
        except Exception as e:
            print(f"❌ Error fetching {ticker}: {e}")
            failed.append(ticker)
            
        # CRITICAL: Sleep for 1 second to avoid getting IP banned by Yahoo Finance
        time.sleep(1) 

    print("\n" + "="*40)
    print(f"✅ Bulk Download Complete!")
    print(f"📈 Successfully saved: {successful} stocks")
    print(f"⚠️ Failed/Delisted: {len(failed)} stocks")
    print("="*40)

if __name__ == "__main__":
    # OPTION A: Test with a small list of top stocks first
    test_tickers = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", 
        "ICICIBANK.NS", "HINDUNILVR.NS", "LATENTVIEW.NS"
    ]
    
    # OPTION B: Load the entire NSE market from the official CSV
    # (Uncomment the 3 lines below once you download EQUITY_L.csv)
    # df_symbols = pd.read_csv("EQUITY_L.csv")
    # # Add the '.NS' suffix that Yahoo Finance requires for Indian stocks
    # full_market_tickers = [str(symbol) + ".NS" for symbol in df_symbols['SYMBOL']]
    # fetch_entire_market(full_market_tickers, years=5)

    # Running the test list for now
    fetch_entire_market(test_tickers, years=5)