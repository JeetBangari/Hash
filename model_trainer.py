import pandas as pd
import numpy as np
import os
import glob
import xgboost as xgb
from sklearn.metrics import classification_report, accuracy_score
import joblib

def train_quant_model():
    input_folder = 'market_data_features'
    csv_files = glob.glob(f"{input_folder}/*.csv")
    
    if not csv_files:
        print("❌ No feature files found. Did you run feature_engineering.py?")
        return

    print(f"📚 Loading data from {len(csv_files)} stocks...")
    
    dataframes = []
    for file in csv_files:
        df = pd.read_csv(file)
        # Ensure the first column (which contains dates) is explicitly named 'Date'
        df.rename(columns={df.columns[0]: 'Date'}, inplace=True) 
        dataframes.append(df)
        
    master_df = pd.concat(dataframes)
    master_df = master_df.dropna()
    
    # --- CRITICAL FIX 1: SORT BY TIME ---
    # We must sort the entire market chronologically before splitting
    print("⏳ Sorting the universe of stocks by time...")
    master_df['Date'] = pd.to_datetime(master_df['Date'])
    master_df = master_df.sort_values(by='Date')
    
    print(f"📊 Total historical market days loaded: {len(master_df):,}")

    features = ['SMA_20', 'SMA_50', 'SMA_200', 'RSI_14', 'MACD', 'MACD_Signal', 'Daily_Return_Pct', 'BB_Position', 'ATR_14', 'Volume_Ratio']
    X = master_df[features]
    y = master_df['Target_14d_Up_2Pct']

    # --- CRITICAL FIX 2: STRICT CHRONOLOGICAL SPLIT ---
    # No random shuffling allowed!
    print("✂️ Splitting data strictly into Past (80% Training) and Future (20% Testing)...")
    split_index = int(len(master_df) * 0.8)
    
    X_train = X.iloc[:split_index]
    X_test = X.iloc[split_index:]
    y_train = y.iloc[:split_index]
    y_test = y.iloc[split_index:]

    print(f"⚔️ Training on {len(X_train)} past days, Testing on {len(X_test)} unseen future days...")

    print("🧠 Initializing XGBoost Quant Model... (This might take a minute)")
    model = xgb.XGBClassifier(
        n_estimators=200,      
        learning_rate=0.05,    
        max_depth=6,           
        random_state=42,
        eval_metric='logloss'
    )

    print("🏋️ Training the model... Please wait.")
    model.fit(X_train, y_train)

    print("🧪 Testing the model on strictly unseen future data...")
    predictions = model.predict(X_test)
    
    accuracy = accuracy_score(y_test, predictions)
    print("\n" + "="*40)
    print(f"🎯 TRUE MODEL ACCURACY: {accuracy * 100:.2f}%")
    print("="*40)
    print("Detailed Report:")
    print(classification_report(y_test, predictions))

    model_filename = "quant_model.joblib"
    joblib.dump(model, model_filename)
    print(f"💾 Model successfully saved as '{model_filename}'")
    print("You can now connect this file to your FastAPI backend!")

if __name__ == "__main__":
    train_quant_model()