import argparse
import os

import joblib
import numpy as np
import pandas as pd
from dataset_d import load_trend_data, preprocess_trend_data
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split, TimeSeriesSplit

MODEL_DIR = os.path.dirname(__file__)
MODEL_PATH = os.path.join(MODEL_DIR, "model_trend.pkl")

def safe_impute(df, is_train=True, train_means=None):
    """
    時系列データのリークを防ぎながら補完を行う
    """
    df = df.copy()
    
    # 1. 前方向埋め (過去の値を引き継ぐ)
    df = df.ffill()
    
    # 2. それでも NaN が残る場合 (データの最初の方など)
    if is_train:
        # 数値型のみを選択して平均を計算
        means = df.select_dtypes(include=[np.number]).mean()
        df = df.fillna(means)
        return df, means
    else:
        if train_means is not None:
            # 指定された数値列のみを補完
            for col in train_means.index:
                if col in df.columns:
                    df[col] = df[col].fillna(train_means[col])
        # さらに残る場合は 0 で埋める（カテゴリ変数等も含む）
        df = df.fillna(0)
        return df

def train_trend_model(include_files=None, exclude_files=None):
    print("SQLiteから釣果データと施設データを結合して読み込み中...")
    df_raw = load_trend_data()
    if df_raw.empty:
        print("エラー: 有効な釣具屋データがロードできませんでした。")
        return

    # 日付順にソート（時系列分割のため）
    df_raw = df_raw.sort_values("date")

    print("データの前処理中...")
    X, y, sample_weights = preprocess_trend_data(df_raw)

    print(f"X shape: {X.shape}, y shape: {y.shape}")

    X_train_raw, X_test_raw, y_train, y_test, w_train, w_test = train_test_split(
        X, y, sample_weights, test_size=0.2, random_state=42, shuffle=False # 時系列なのでシャッフルしないのが無難
    )

    print("欠損値の補完中 (Leakage対策)...")
    X_train, train_means = safe_impute(X_train_raw, is_train=True)
    X_test = safe_impute(X_test_raw, is_train=False, train_means=train_means)

    print("交差検証 (TimeSeriesSplit) を実行中...")
    tscv = TimeSeriesSplit(n_splits=5)
    cv_r2 = []
    cv_mse = []
    
    # DataFrameのインデックスをリセットしてCV分割しやすくする
    X_cv = X.reset_index(drop=True)
    y_cv = y.reset_index(drop=True)
    w_cv = sample_weights.reset_index(drop=True)
    
    for train_index, test_index in tscv.split(X_cv):
        X_tr_raw, X_te_raw = X_cv.iloc[train_index], X_cv.iloc[test_index]
        y_tr, y_te = y_cv.iloc[train_index], y_cv.iloc[test_index]
        w_tr = w_cv.iloc[train_index]
        
        X_tr, means = safe_impute(X_tr_raw, is_train=True)
        X_te = safe_impute(X_te_raw, is_train=False, train_means=means)
        
        cv_model = RandomForestRegressor(n_estimators=100, random_state=42)
        cv_model.fit(X_tr, y_tr, sample_weight=w_tr)
        
        p_te = cv_model.predict(X_te)
        cv_r2.append(r2_score(y_te, p_te))
        cv_mse.append(mean_squared_error(y_te, p_te))
        
    print(f"  🔍 CV R2: {np.mean(cv_r2):.4f} ± {np.std(cv_r2):.4f}, MSE: {np.mean(cv_mse):.4f} ± {np.std(cv_mse):.4f}\n")

    print("本番モデルの学習とホールドアウト評価中 (RandomForestRegressor)...")
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    # ここで weight（施設1.0, 釣具屋0.3等）を sample_weight として渡すことでAIが施設データをより重視する
    model.fit(X_train, y_train, sample_weight=w_train)

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
