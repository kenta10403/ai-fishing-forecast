import argparse
import os

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
    period_averages = model_data.get("period_averages", {})
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
        df['day'] = df['date'].dt.day
        df['day_of_week'] = df['date'].dt.dayofweek

        def calc_period(row):
            if pd.isna(row['month']) or pd.isna(row['day']):
                return 1
            m = int(row['month'])
            d = int(row['day'])
            part = 0 if d <= 10 else 1 if d <= 20 else 2
            return (m - 1) * 3 + part + 1

        df['period_of_year'] = df.apply(calc_period, axis=1)
        period_val = int(df['period_of_year'].iloc[0])

        def simplify_weather(w):
            if "晴" in w: return "晴れ"
            if "雨" in w: return "雨"
            if "曇" in w: return "曇り"
            return "その他"

        df['weather_simple'] = df['weather'].apply(simplify_weather)

        encode_cols = ['area', 'weather_simple', 'species']
        X = df[['period_of_year', 'day_of_week'] + encode_cols]
        X = pd.get_dummies(X, columns=encode_cols)
        X = X.reindex(columns=feature_cols, fill_value=0)

        # トレンドの熱量（生スコア）
        raw_trend = float(model.predict(X)[0])
        raw_trend = max(0.0, raw_trend)

        # 相対トレンド（確変度: 平均の何倍か）を計算
        avg_key = f"{period_val}_{sp}"
        baseline_avg = period_averages.get(avg_key, 1.0) # ない場合は1.0とする
        if baseline_avg <= 0:
            baseline_avg = 1.0

        relative_trend = raw_trend / baseline_avg

        # 過去データから「その魚がどれくらいバズっている状態か」を100点満点化
        if len(score_distribution) > 0:
            pct_score = stats.percentileofscore(score_distribution, raw_trend, kind='weak')
        else:
            pct_score = 0.0

        ranking.append((sp, pct_score, raw_trend, relative_trend))

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

        for i, (sp, pct_score, raw, rel_trend) in enumerate(ranking, 1):
            if raw < 5.0: # トレンドがほぼない魚（生スコアが極端に低い）は除外してスッキリさせる
                continue

            # 確変メッセージ
            if rel_trend >= 2.0:
                trend_msg = f"🔥超確変中({rel_trend:.1f}倍)🔥"
            elif rel_trend >= 1.5:
                trend_msg = f"✨確変中({rel_trend:.1f}倍)"
            elif rel_trend >= 1.2:
                trend_msg = f"↑上昇傾向({rel_trend:.1f}倍)"
            else:
                trend_msg = f"平年並み({rel_trend:.1f}倍)"

            print(f" {i}位: {sp} (★ 活性度: {pct_score:.1f}点 / {trend_msg} / トレンド熱量: {raw:.1f})")

        print("===" * 10)
        print("※ このランキングは釣った人の『報告の多さ』をベースにしたトレンド目安です。")
    except Exception as e:
        print(f"実行エラー: {e}")
