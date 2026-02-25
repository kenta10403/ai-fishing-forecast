import os
import argparse
import joblib
import pandas as pd
from typing import Dict, Any

MODEL_FILE_NAME = "model_cpue_total.pkl"  # デフォルト（引数でターゲット名受け取る処理等がなければ）
MODEL_PATH = os.path.join(os.path.dirname(__file__), MODEL_FILE_NAME)

import scipy.stats as stats

def get_prediction_and_score(date_str: str, facility_name: str, weather: str, water_temp: float, tide: str) -> tuple:
    """
    保存されたモデルを用いて予測を行い、(生スコア, 100点満点の爆釣スコア) のタプルを返す
    """
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"モデルファイルが見つかりません: {MODEL_PATH}。先に train.py を実行してください。")
        
    model_data = joblib.load(MODEL_PATH)
    model = model_data["model"]
    feature_cols = model_data["features"]
    score_distribution = model_data.get("score_distribution", [])
    
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
    df.fillna({'water_temp': water_temp}, inplace=True)
    
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
    X = pd.get_dummies(X, columns=encode_cols)
    X = X.reindex(columns=feature_cols, fill_value=0)
    
    # 推論 (1人あたりの予測釣果: CPUE)
    pred_cpue = float(model.predict(X)[0])
    pred_cpue = max(0.0, pred_cpue)
    
    # パーセンタイル（100点満点）に変換
    # 過去の分布の中で、この推論値がどの位置（下から何％か）にあたるかを算出
    if len(score_distribution) > 0:
        percentile_score = stats.percentileofscore(score_distribution, pred_cpue, kind='weak')
    else:
        percentile_score = 0.0
        
    return pred_cpue, percentile_score

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="釣果の予測実行スクリプト")
    parser.add_argument("--date", type=str, required=True, help="釣行予定日 (YYYY/MM/DD)")
    parser.add_argument("--facility", type=str, required=True, help="施設名 (例: daikoku)")
    parser.add_argument("--weather", type=str, required=True, help="天気 (例: 晴れ)")
    parser.add_argument("--temp", type=float, required=True, help="水温 (例: 15.0)")
    parser.add_argument("--tide", type=str, required=True, help="潮回り (例: 大潮)")
    
    args = parser.parse_args()
    
    try:
        raw_cpue, pct_score = get_prediction_and_score(args.date, args.facility, args.weather, args.temp, args.tide)
        print("===" * 10)
        print(f"予測結果 (爆釣指数: 100点満点)")
        print(f" 条件: {args.date} | {args.facility} | {args.weather} | 水温 {args.temp}℃ | {args.tide}")
        print(f" \n ★ 爆釣指数: {pct_score:.1f} / 100点")
        print(f"   (参考) 1人あたりの推定釣果数: {raw_cpue:.2f} 匹")
        print("===" * 10)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
