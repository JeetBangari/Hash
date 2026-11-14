import pandas as pd
import numpy as np
import os
import glob

def calculate_rsi(data, window=14):
    """Calculates the Relative Strength Index (RSI)"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, window=14):
    """Calculates Average True Range (Volatility)"""
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(window).mean()

def process_market_data():
    input_folder = 'market_data_5Y'
    output_folder = 'market_data_features'
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    csv_files = glob.glob(f"{input_folder}/*.csv")
    print(f"⚙️ Upgrading features for {len(csv_files)} stocks...")
    
    successful = 0
    
    for file in csv_files:
        try:
            df = pd.read_csv(file, index_col=0)
            
            # Require at least 200 days of data to calculate the SMA_200
            if len(df) < 200:
                continue
                
            # --- 1. BASE TREND INDICATORS ---
            df['SMA_20'] = df['Close'].rolling(window=20).mean()
            df['SMA_50'] = df['Close'].rolling(window=50).mean()
            df['SMA_200'] = df['Close'].rolling(window=200).mean()
            
            df['RSI_14'] = calculate_rsi(df['Close'])
            
            exp1 = df['Close'].ewm(span=12, adjust=False).mean()
            exp2 = df['Close'].ewm(span=26, adjust=False).mean()
            df['MACD'] = exp1 - exp2
            df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
            
            # --- 2. ADVANCED: BOLLINGER BANDS (Mean Reversion) ---
            df['BB_Std'] = df['Close'].rolling(window=20).std()
            df['BB_Upper'] = df['SMA_20'] + (df['BB_Std'] * 2)
            df['BB_Lower'] = df['SMA_20'] - (df['BB_Std'] * 2)
            # Normalizes position: 0 = at lower band, 1 = at upper band
            df['BB_Position'] = (df['Close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'])
            
            # --- 3. ADVANCED: ATR (Volatility) ---
            df['ATR_14'] = calculate_atr(df)
            
            # --- 4. ADVANCED: VOLUME SPIKES (Smart Money Tracker) ---
            df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
            df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA_20'] # Values > 1.5 indicate heavy buying/selling
            
            df['Daily_Return_Pct'] = df['Close'].pct_change() * 100
            
            # --- 5. THE STRICT TARGET (14 Days, >2% Gain) ---
            df['Future_14d_Close'] = df['Close'].shift(-14)
            df['Future_Return_Pct'] = ((df['Future_14d_Close'] - df['Close']) / df['Close']) * 100
            
            # 1 = Stock went up at least 2% in the next 14 days. 0 = It didn't.
            df['Target_14d_Up_2Pct'] = (df['Future_Return_Pct'] > 2.0).astype(int)
            
            # Clean up
            df = df.dropna()
            filename = os.path.basename(file)
            df.to_csv(f"{output_folder}/{filename}")
            successful += 1
            
        except Exception as e:
            print(f"Error processing {file}: {e}")
            
    print("\n" + "="*40)
    print(f"✅ Advanced Feature Engineering Complete!")
    print(f"🧠 {successful} stocks are now pumped with institutional-grade metrics.")
    print("="*40)

if __name__ == "__main__":
    process_market_data()