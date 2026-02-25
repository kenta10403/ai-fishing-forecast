import argparse
import os

import joblib
import pandas as pd
import scipy.stats as stats

MODEL_DIR = os.path.dirname(__file__)
FACILITIES = ["daikoku", "isogo", "honmoku", "ichihara"]

def recommend_best_facility(target_species: str, date_str: str, weather: str, water_temp: float, tide: str):

    # 1. 本命：対象の魚種専用モデル（施設データ）を探す
    model_name = "model_cpue_" + target_species + ".pkl"
    model_path = os.path.join(MODEL_DIR, model_name)

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"モデルファイルが見つかりません: {model_path}。\n"
            f"先に 'python3 src/ml/train.py --target {target_species}' を実行してください。"
        )

    model_data = joblib.load(model_path)
    model = model_data["model"]
    feature_cols = model_data["features"]
    score_distribution = model_data.get("score_distribution", [])
    period_averages = model_data.get("period_averages", {})

    # 2. ブースト用：トレンドモデル（釣具屋データ）を探す
    trend_model_path = os.path.join(MODEL_DIR, "model_trend.pkl")
    trend_boost_multiplier = 1.0
    trend_msg = ""

    if os.path.exists(trend_model_path):
        trend_data = joblib.load(trend_model_path)
        t_model = trend_data["model"]
        t_features = trend_data["features"]
        t_period_avgs = trend_data.get("period_averages", {})

        # 代表エリア（ここでは広域に強い東京・神奈川を含めたダミーエリア）でトレンドを判定
        t_input = {
            "date": [date_str], "area": ["神奈川県"], "weather": [weather], "species": [target_species]
        }
        t_df = pd.DataFrame(t_input)
        t_df['date'] = pd.to_datetime(t_df['date'], errors='coerce')
        t_df['month'] = t_df['date'].dt.month
        t_df['day'] = t_df['date'].dt.day
        t_df['day_of_week'] = t_df['date'].dt.dayofweek

        def calc_t_period(row):
            if pd.isna(row['month']) or pd.isna(row['day']): return 1
            m, d = int(row['month']), int(row['day'])
            return (m - 1) * 3 + (0 if d <= 10 else 1 if d <= 20 else 2) + 1

        t_df['period_of_year'] = t_df.apply(calc_t_period, axis=1)
        period_val = int(t_df['period_of_year'].iloc[0])

        def simplify_w(w):
            if "晴" in w: return "晴れ"
            if "雨" in w: return "雨"
            if "曇" in w: return "曇り"
            return "その他"

        t_df['weather_simple'] = t_df['weather'].apply(simplify_w)
        encode_cols_t = ['area', 'weather_simple', 'species']
        t_X = t_df[['period_of_year', 'day_of_week'] + encode_cols_t]
        t_X = pd.get_dummies(t_X, columns=encode_cols_t)
        t_X = t_X.reindex(columns=t_features, fill_value=0)

        t_pred = float(t_model.predict(t_X)[0])
        t_avg_key = f"{period_val}_{target_species}"
        t_baseline = t_period_avgs.get(t_avg_key, 1.0)
        if t_baseline <= 0: t_baseline = 1.0

        trend_ratio = t_pred / t_baseline
        if trend_ratio >= 2.0:
            trend_boost_multiplier = 1.3 # 30%スコアアップ！超確変
            trend_msg = f"超確変中({trend_ratio:.1f}倍)"
        elif trend_ratio >= 1.5:
            trend_boost_multiplier = 1.15 # 15%スコアアップ
            trend_msg = f"確変中({trend_ratio:.1f}倍)"
        elif trend_ratio >= 1.2:
            trend_boost_multiplier = 1.05
            trend_msg = f"上昇傾向({trend_ratio:.1f}倍)"

    # 3. 施設それぞれのシミュレーションとブースト合算
    ranking = []

    for facility in FACILITIES:
        input_data = {
            "date": [date_str], "facility": [facility], "weather": [weather],
            "water_temp": [water_temp], "tide": [tide]
        }

        df = pd.DataFrame(input_data)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df['month'] = df['date'].dt.month
        df['day'] = df['date'].dt.day
        df['day_of_week'] = df['date'].dt.dayofweek
        df['water_temp'] = pd.to_numeric(df['water_temp'], errors='coerce')
        df.fillna({'water_temp': water_temp}, inplace=True)

        df['period_of_year'] = df.apply(lambda row:
            1 if pd.isna(row['month']) else
            (int(row['month']) - 1) * 3 + (0 if int(row['day']) <= 10 else 1 if int(row['day']) <= 20 else 2) + 1, axis=1)

        p_val = int(df['period_of_year'].iloc[0])

        def simplify_weather(w):
            if "晴" in w: return "晴れ"
            if "雨" in w: return "雨"
            if "曇" in w: return "曇り"
            return "その他"

        df['weather_simple'] = df['weather'].apply(simplify_weather)

        encode_cols = ['facility', 'weather_simple', 'tide']
        X = df[['period_of_year', 'day_of_week', 'water_temp'] + encode_cols]
        X = pd.get_dummies(X, columns=encode_cols)
        X = X.reindex(columns=feature_cols, fill_value=0)

        # 生スコア（釣果の絶対数：ボウズ逃れ指標）
        pred_cpue = max(0.0, float(model.predict(X)[0]))

        # 施設の過去平均に対する相対トレンド
        baseline_avg = period_averages.get(p_val, 1.0)
        if baseline_avg <= 0: baseline_avg = 1.0
        facility_relative_ratio = pred_cpue / baseline_avg

        pct_score = stats.percentileofscore(score_distribution, pred_cpue, kind='weak') if len(score_distribution) > 0 else 0.0

        # ★ 神予測ロジック: 施設ベーススコア × SNSトレンドブースト
        final_boosted_score = pct_score * trend_boost_multiplier
        # 100点満点をオーバーした場合は100までに収める
        final_boosted_score = min(100.0, final_boosted_score)

        ranking.append((facility, final_boosted_score, pct_score, pred_cpue, facility_relative_ratio))

    ranking.sort(key=lambda x: x[1], reverse=True)
    return ranking, trend_boost_multiplier, trend_msg

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="指定魚種を狙うための最適な釣り場ランキング検索 (パターンC)")
    parser.add_argument("--target", type=str, required=True, help="狙いたい魚種 (例: アジ)")
    parser.add_argument("--date", type=str, required=True, help="釣行予定日 (YYYY/MM/DD)")
    parser.add_argument("--weather", type=str, required=True, help="天気 (例: 晴れ)")
    parser.add_argument("--temp", type=float, required=True, help="水温 (例: 15.0)")
    parser.add_argument("--tide", type=str, required=True, help="潮回り (例: 大潮)")

    args = parser.parse_args()

    try:
        ranking, boost_mult, trend_msg = recommend_best_facility(args.target, args.date, args.weather, args.temp, args.tide)
        print("===" * 13)
        print(f"🎣 【{args.target} を狙うならここ！神予測 最適釣り場ランキング】 🎣")
        print(f" 条件: {args.date} | {args.weather} | 水温 {args.temp}℃ | {args.tide}")
        if trend_msg:
            print(f" 🚨 SNSトレンド検知！今の {args.target} は周りで {trend_msg}！！")
            print(f"    (施設スコアに x{boost_mult:.2f} のトレンドボーナスを加算して評価中🔥)")
        print("===" * 13)

        for i, (facility, boosted_score, pct_score, raw_cpue, f_ratio) in enumerate(ranking, 1):
            fname = "大黒" if facility == "daikoku" else \
                    "本牧" if facility == "honmoku" else \
                    "磯子" if facility == "isogo" else \
                    "市原" if facility == "ichihara" else facility

            print(f" {i}位: {fname} (★ 総合爆釣指数: {boosted_score:.1f}点) [ベース期待: {raw_cpue:.2f}匹/人, 施設内確変度: {f_ratio:.1f}倍]")
        print("===" * 13)
    except Exception as e:
        print(f"実行エラー: {e}")
