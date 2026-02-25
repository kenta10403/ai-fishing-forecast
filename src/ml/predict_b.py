import os
import argparse
import joblib
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_b.pkl")

def predict_ranking(date_str: str, facility_name: str, weather: str, water_temp: float, tide: str):
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"モデルファイルが見つかりません: {MODEL_PATH}。先に train_b.py を実行してください。")
        
    model_data = joblib.load(MODEL_PATH)
    model = model_data["model"]
    feature_cols = model_data["features"]
    target_species = model_data["targets"]
    
    input_data = {
        "date": [date_str],
        "facility": [facility_name],
        "weather": [weather],
        "water_temp": [water_temp],
        "tide": [tide]
    }
    
    df = pd.DataFrame(input_data)
    
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['month'] = df['date'].dt.month
    df['day_of_week'] = df['date'].dt.dayofweek
    df.fillna({'water_temp':water_temp}, inplace=True)
    
    def simplify_weather(w):
        if "晴" in w: return "晴れ"
        if "雨" in w: return "雨"
        if "曇" in w: return "曇り"
        return "その他"
        
    df['weather_simple'] = df['weather'].apply(simplify_weather)
    
    encode_cols = ['facility', 'weather_simple', 'tide']
    X = df[['month', 'day_of_week', 'water_temp'] + encode_cols]
    
    X = pd.get_dummies(X, columns=encode_cols)
    X = X.reindex(columns=feature_cols, fill_value=0)
    
    # 推論 (各ターゲット変数の予測値の配列が返る)
    pred = model.predict(X)[0]
    
    # 魚種と予測スコアを紐付け
    ranking = []
    for sp, score in zip(target_species, pred):
        ranking.append((sp, max(0, float(score))))
        
    # スコアが大きい順にソート
    ranking.sort(key=lambda x: x[1], reverse=True)
    
    return ranking

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="釣れそうな魚ランキング予測 (パターンB)")
    parser.add_argument("--date", type=str, required=True, help="釣行予定日 (YYYY/MM/DD)")
    parser.add_argument("--facility", type=str, required=True, help="施設名 (例: daikoku)")
    parser.add_argument("--weather", type=str, required=True, help="天気 (例: 晴れ)")
    parser.add_argument("--temp", type=float, required=True, help="水温 (例: 15.0)")
    parser.add_argument("--tide", type=str, required=True, help="潮回り (例: 大潮)")
    
    args = parser.parse_args()
    
    ranking = predict_ranking(args.date, args.facility, args.weather, args.temp, args.tide)
    
    print("===" * 10)
    print(f"【釣れそうな魚ランキング予測】")
    print(f" 条件: {args.date} | {args.facility} | {args.weather} | 水温 {args.temp}℃ | {args.tide}")
    print("===" * 10)
    for i, (sp, score) in enumerate(ranking, 1):
        if score > 0.1:  # 0に近いスコアは足切り
            print(f" {i}位: {sp} (期待値スコア: {score:.1f})")
    print("===" * 10)
