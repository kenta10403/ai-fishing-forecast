import os
import argparse
import joblib
import pandas as pd

# predict_c.pyは既存のtrain.pyで作成された各種モデル（例：model_アジ.pkl）を利用する
MODEL_DIR = os.path.dirname(__file__)

# 評価対象施設リスト（現在取得している代表的な施設）
FACILITIES = ["daikoku", "isogo", "honmoku", "ichihara"]

def recommend_best_facility(target_species: str, date_str: str, weather: str, water_temp: float, tide: str):
    
    # 対象の魚種専用モデルを探す
    model_name = "model_" + target_species + ".pkl"
    model_path = os.path.join(MODEL_DIR, model_name)
    
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"モデルファイルが見つかりません: {model_path}。\n"
            f"先に 'python3 src/ml/train.py --target {target_species}' を実行して専用モデルを作成してください。"
        )
        
    model_data = joblib.load(model_path)
    model = model_data["model"]
    feature_cols = model_data["features"]
    
    ranking = []
    
    # 全施設に対してシミュレーション
    for facility in FACILITIES:
        input_data = {
            "date": [date_str],
            "facility": [facility],
            "weather": [weather],
            "water_temp": [water_temp],
            "tide": [tide]
        }
        
        df = pd.DataFrame(input_data)
        
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
        
        encode_cols = ['facility', 'weather_simple', 'tide']
        X = df[['month', 'day_of_week', 'water_temp'] + encode_cols]
        
        X = pd.get_dummies(X, columns=encode_cols)
        X = X.reindex(columns=feature_cols, fill_value=0)
        
        # 期待スコアを算出
        pred = model.predict(X)[0]
        score = max(0, float(pred))
        
        ranking.append((facility, score))
        
    # スコアが大きい順にソート
    ranking.sort(key=lambda x: x[1], reverse=True)
    return ranking

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="指定魚種を狙うための最適な釣り場ランキング検索 (パターンC)")
    parser.add_argument("--target", type=str, required=True, help="狙いたい魚種 (例: アジ)")
    parser.add_argument("--date", type=str, required=True, help="釣行予定日 (YYYY/MM/DD)")
    parser.add_argument("--weather", type=str, required=True, help="天気 (例: 晴れ)")
    parser.add_argument("--temp", type=float, required=True, help="水温 (例: 15.0)")
    parser.add_argument("--tide", type=str, required=True, help="潮回り (例: 大潮)")
    
    args = parser.parse_args()
    
    try:
        ranking = recommend_best_facility(args.target, args.date, args.weather, args.temp, args.tide)
        print("===" * 10)
        print(f"【{args.target} を狙うならここ！ 最適釣り場ランキング】")
        print(f" 条件: {args.date} | {args.weather} | 水温 {args.temp}℃ | {args.tide}")
        print("===" * 10)
        
        for i, (facility, score) in enumerate(ranking, 1):
            # 施設名を分かりやすく変換
            fname = "大黒" if facility == "daikoku" else \
                    "本牧" if facility == "honmoku" else \
                    "磯子" if facility == "isogo" else \
                    "市原" if facility == "ichihara" else facility
                    
            print(f" {i}位: {fname} (期待値スコア: {score:.1f})")
        print("===" * 10)
    except Exception as e:
        print(f"実行エラー: {e}")
