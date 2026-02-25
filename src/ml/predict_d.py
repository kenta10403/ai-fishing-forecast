import os
import argparse
import joblib
import pandas as pd
import scipy.stats as stats

MODEL_DIR = os.path.dirname(__file__)
MODEL_PATH = os.path.join(MODEL_DIR, "model_trend.pkl")

def get_trend_ranking(date_str: str, area: str, weather: str):
    """
    指定日の『エリアのトレンド（どの魚種が盛り上がっているか）』を予測する
    """
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"モデルが見つかりません: {MODEL_PATH}。先に train_d.py を実行してください。")
        
    model_data = joblib.load(MODEL_PATH)
    model = model_data["model"]
    feature_cols = model_data["features"]
    score_distribution = model_data.get("score_distribution", [])
    species_list = model_data.get("species_list", [])
    
    if not species_list:
        raise ValueError("モデルに予測対象の魚種リストが組み込まれていません")
        
    ranking = []
    
    # 対象エリアの全ての魚種の活性をシミュレーション
    for sp in species_list:
        input_data = {
            "date": [date_str],
            "area": [area],
            "weather": [weather],
            "species": [sp]
        }
        
        df = pd.DataFrame(input_data)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df['month'] = df['date'].dt.month
        df['day_of_week'] = df['date'].dt.dayofweek
        
        def simplify_weather(w):
            if "晴" in w: return "晴れ"
            if "雨" in w: return "雨"
            if "曇" in w: return "曇り"
            return "その他"
            
        df['weather_simple'] = df['weather'].apply(simplify_weather)
        
        encode_cols = ['area', 'weather_simple', 'species']
        X = df[['month', 'day_of_week'] + encode_cols]
        X = pd.get_dummies(X, columns=encode_cols)
        X = X.reindex(columns=feature_cols, fill_value=0)
        
        # トレンドの熱量（生スコア）
        raw_trend = float(model.predict(X)[0])
        raw_trend = max(0.0, raw_trend)
        
        # 過去データから「その魚がどれくらいバズっている状態か」を100点満点化
        if len(score_distribution) > 0:
            pct_score = stats.percentileofscore(score_distribution, raw_trend, kind='weak')
        else:
            pct_score = 0.0
            
        ranking.append((sp, pct_score, raw_trend))
        
    # 生の熱量（raw_trend）でソート（同じパーセンタイルに丸まることがあるため）
    ranking.sort(key=lambda x: x[2], reverse=True)
    return ranking

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SNS・釣具屋トレンドのランキング予測 (パターンD)")
    parser.add_argument("--date", type=str, required=True, help="釣行予定日 (YYYY/MM/DD)")
    parser.add_argument("--area", type=str, required=True, help="エリア名 (例: 千葉県, 福岡県 等。モデルの学習地域に依存)")
    parser.add_argument("--weather", type=str, required=True, help="天気 (例: 晴れ)")
    
    args = parser.parse_args()
    
    try:
        ranking = get_trend_ranking(args.date, args.area, args.weather)
        print("===" * 10)
        print(f"🔥 【いま話題！ {args.area} の魚種トレンド予測】 🔥")
        print(f" 条件: {args.date} | {args.weather}")
        print("===" * 10)
        
        for i, (sp, pct_score, raw) in enumerate(ranking, 1):
            if raw < 5.0: # トレンドがほぼない魚（生スコアが極端に低い）は除外してスッキリさせる
                continue
            print(f" {i}位: {sp} (★ 活性度: {pct_score:.1f}点 / トレンド熱量: {raw:.1f})")
            
        print("===" * 10)
        print("※ このランキングは釣った人の『報告の多さ』をベースにしたトレンド目安です。")
    except Exception as e:
        print(f"実行エラー: {e}")
