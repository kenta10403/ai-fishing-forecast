import argparse
import os

import joblib
import numpy as np
import pandas as pd
from dataset_d import load_trend_data, preprocess_trend_data
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

MODEL_DIR = os.path.dirname(__file__)
MODEL_PATH = os.path.join(MODEL_DIR, "model_trend.pkl")

def train_trend_model(include_files=None, exclude_files=None):
    print("釣具屋トレンドデータ(パターンD)の読み込みと日次集計中...")
    df_raw = load_trend_data(include_files, exclude_files)
    if df_raw.empty:
        print("エラー: 有効な釣具屋データがロードできませんでした。")
        return

    print("データの前処理中...")
    X, y = preprocess_trend_data(df_raw)

    print(f"X shape: {X.shape}, y shape: {y.shape}")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("モデルの学習中 (RandomForestRegressor)...")
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    pred_test = model.predict(X_test)
    mse = mean_squared_error(y_test, pred_test)
    r2 = r2_score(y_test, pred_test)

    print("学習完了!")
    print(f" - Test MSE: {mse:.4f}")
    print(f" - Test R2 Score: {r2:.4f} (※バイアスの強いデータなので参考値)")

    # トレンド指数の規模感（パーセンタイル）を出すための分布を保存
    score_distribution = np.sort(y_train.values)

    # 36期(period_of_year) × 魚種(species) ごとの平均トレンドスコアを算出
    period_species_avg = df_raw.groupby(['period_of_year', 'species'])['trend_score'].mean().to_dict()
    period_avg_dict = {f"{k[0]}_{k[1]}": v for k, v in period_species_avg.items()}

    # --- 36期(period_of_year) ごとの「シーズナルのポテンシャル」を算出 ---
    # 「何かしら釣れるかどうか」が基準なので、施設のCPUE（一人あたり釣果）を主軸にする。
    # 施設データはバイアスが少なく最も信頼できる。
    # 施設データがない期間だけ、釣具屋データで補完する。

    df_raw['month'] = ((df_raw['period_of_year'] - 1) // 3) + 1
    
    # 施設データだけで月別・期別の平均CPUEを算出
    facility_data = df_raw[df_raw['is_facility'] == True]
    shop_data = df_raw[df_raw['is_facility'] == False]
    
    facility_month_avg = facility_data.groupby('month')['trend_score'].mean() if len(facility_data) > 0 else pd.Series(dtype=float)
    facility_period_avg = facility_data.groupby('period_of_year')['trend_score'].mean() if len(facility_data) > 0 else pd.Series(dtype=float)
    
    # 釣具屋データはフォールバック用
    shop_month_avg = shop_data.groupby('month')['trend_score'].mean() if len(shop_data) > 0 else pd.Series(dtype=float)
    global_avg = df_raw['trend_score'].mean()

    seasonal_potential = {}
    for p in range(1, 37):
        m = ((p - 1) // 3) + 1
        
        # 施設の期別データがあればそれを最優先
        if p in facility_period_avg.index and not pd.isna(facility_period_avg.get(p)):
            p_val = facility_period_avg.get(p)
        elif m in facility_month_avg.index and not pd.isna(facility_month_avg.get(m)):
            p_val = facility_month_avg.get(m)
        elif m in shop_month_avg.index:
            p_val = shop_month_avg.get(m)
        else:
            p_val = global_avg
        
        # 施設の月平均があれば平滑化のベースに使う
        if m in facility_month_avg.index and not pd.isna(facility_month_avg.get(m)):
            m_val = facility_month_avg.get(m)
        elif m in shop_month_avg.index:
            m_val = shop_month_avg.get(m)
        else:
            m_val = global_avg
        
        # 平滑化: 月平均 60% + 期別 40%（施設データ中心なのでノイズ少なく、期別の影響を少し強めに）
        seasonal_potential[p] = (m_val * 0.6) + (p_val * 0.4)

    # 正規化 (90パーセンタイルを1.0とする)
    vals = list(seasonal_potential.values())
    baseline = np.percentile(vals, 90) if vals else 1.0
    seasonal_potential_dict = {str(k): v / baseline for k, v in seasonal_potential.items()}

    # 5. 36期(period_of_year) ごとの平均水温も算出しておく（予測時のデフォルト値用）
    period_water_temp_avg = df_raw.groupby('period_of_year')['water_temp'].mean().to_dict()
    period_water_temp_dict = {str(k): v for k, v in period_water_temp_avg.items()}

    # 使用された特徴量のカラムと、ユニークな魚種リスト・エリアリストも記録しておく
    model_data = {
        "model": model,
        "features": X.columns.tolist(),
        "score_distribution": score_distribution,
        "period_averages": period_avg_dict,
        "period_water_temps": period_water_temp_dict,
        "seasonal_potential": seasonal_potential_dict,
        "species_list": sorted(df_raw['species'].unique().tolist()),
        "areas": sorted(df_raw['area'].unique().tolist())
    }

    joblib.dump(model_data, MODEL_PATH)
    print(f"トレンド予測モデルを {MODEL_PATH} に保存しました。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="釣具屋データからのSNSトレンド予測モデル学習")
    parser.add_argument("--include", nargs="+", help="対象JSONファイル（未指定でcastingとjohshuya）")

    args = parser.parse_args()
    train_trend_model(include_files=args.include)
