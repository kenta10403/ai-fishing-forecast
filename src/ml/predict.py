import os
import argparse
import joblib
import pandas as pd
from typing import Dict, Any

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")

def get_prediction(date_str: str, facility_name: str, weather: str, water_temp: float, tide: str) -> float:
    """
    保存されたモデルを用いて予測を行う
    """
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"モデルファイルが見つかりません: {MODEL_PATH}。先に train.py を実行してください。")
        
    model_data = joblib.load(MODEL_PATH)
    model = model_data["model"]
    feature_cols = model_data["features"]
    
    # 入力データから DataFrame を作成
    input_data = {
        "date": [date_str],
        "facility": [facility_name],
        "weather": [weather],
        "water_temp": [water_temp],
        "tide": [tide]
    }
    
    df = pd.DataFrame(input_data)
    
    # dataset.pyと同じ前処理
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['month'] = df['date'].dt.month
    df['day_of_week'] = df['date'].dt.dayofweek
    df['water_temp'] = pd.to_numeric(df['water_temp'], errors='coerce')
    
    def simplify_weather(w):
        if "晴" in w: return "晴れ"
        if "雨" in w: return "雨"
        if "曇" in w: return "曇り"
        return "その他"
        
    df['weather_simple'] = df['weather'].apply(simplify_weather)
    
    # 必要な列だけ抽出して One-Hot Encoding
    encode_cols = ['facility', 'weather_simple', 'tide']
    X = df[['month', 'day_of_week', 'water_temp'] + encode_cols]
    
    # カテゴリ変数をダミー変数化 (PD.get_dummies)
    # 訓練時と同じカラムに合わせるため、reindexを使用
    X = pd.get_dummies(X, columns=encode_cols)
    X = X.reindex(columns=feature_cols, fill_value=0)
    
    # 推論
    pred = model.predict(X)
    return max(0, float(pred[0]))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="釣果の予測実行スクリプト")
    parser.add_argument("--date", type=str, required=True, help="釣行予定日 (YYYY/MM/DD)")
    parser.add_argument("--facility", type=str, required=True, help="施設名 (例: daikoku)")
    parser.add_argument("--weather", type=str, required=True, help="天気 (例: 晴れ)")
    parser.add_argument("--temp", type=float, required=True, help="水温 (例: 15.0)")
    parser.add_argument("--tide", type=str, required=True, help="潮回り (例: 大潮)")
    
    args = parser.parse_args()
    
    try:
        score = get_prediction(args.date, args.facility, args.weather, args.temp, args.tide)
        print("===" * 10)
        print(f"予測結果")
        print(f" 条件: {args.date} | {args.facility} | {args.weather} | 水温 {args.temp}℃ | {args.tide}")
        print(f" 予測スコア(釣果期待値): {score:.1f}")
        print("===" * 10)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
