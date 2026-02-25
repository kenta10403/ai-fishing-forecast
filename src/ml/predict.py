import argparse
import os

import joblib
import pandas as pd

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
    period_averages = model_data.get("period_averages", {})

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

    # 必要な列だけ抽出して One-Hot Encoding
    encode_cols = ['facility', 'weather_simple', 'tide']
    X = df[['period_of_year', 'day_of_week', 'water_temp'] + encode_cols]

    # カテゴリ変数をダミー変数化 (PD.get_dummies)
    X = pd.get_dummies(X, columns=encode_cols)
    X = X.reindex(columns=feature_cols, fill_value=0)

    # 推論 (1人あたりの予測釣果: CPUE)
    pred_cpue = float(model.predict(X)[0])
    pred_cpue = max(0.0, pred_cpue)

    # パーセンタイル（100点満点）に変換
    # 過去の分布の中で、この推論値がどの位置（下から何％か）にあたるかを算出
    if len(score_distribution) > 0:
        pct_score = stats.percentileofscore(score_distribution, pred_cpue, kind='weak')
    else:
        pct_score = 0.0

    # 施設の過去平均に対する相対トレンド（確変度）
    baseline_avg = period_averages.get(p_val, 1.0)
    if baseline_avg <= 0: baseline_avg = 1.0
    relative_ratio = pred_cpue / baseline_avg

    return pred_cpue, pct_score, relative_ratio

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="釣果の予測実行スクリプト")
    parser.add_argument("--date", type=str, required=True, help="釣行予定日 (YYYY/MM/DD)")
    parser.add_argument("--facility", type=str, required=True, help="施設名 (例: daikoku)")
    parser.add_argument("--weather", type=str, required=True, help="天気 (例: 晴れ)")
    parser.add_argument("--temp", type=float, required=True, help="水温 (例: 15.0)")
    parser.add_argument("--tide", type=str, required=True, help="潮回り (例: 大潮)")

    args = parser.parse_args()

    try:
        raw_cpue, pct_score, relative_ratio = get_prediction_and_score(args.date, args.facility, args.weather, args.temp, args.tide)
        print("===" * 10)
        print("予測結果 (ボウズ逃れ指数: 100点満点)")
        print(f" 条件: {args.date} | {args.facility} | {args.weather} | 水温 {args.temp}℃ | {args.tide}")
        print(f" \n ★ ボウズ逃れ指数(絶対数): {pct_score:.1f} / 100点")
        print(f"   (参考) 1人あたりの推定釣果数: {raw_cpue:.2f} 匹")
        print(f"   (参考) 施設内の確変度(相対トレンド): 平年の {relative_ratio:.1f} 倍")
        print("===" * 10)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
