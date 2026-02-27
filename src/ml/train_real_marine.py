import argparse
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.multioutput import MultiOutputRegressor
from sklearn.ensemble import RandomForestRegressor
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

# --- Dataset Loading ---
from dataset_real_marine import create_dataset

MODEL_DIR = os.path.dirname(__file__)
MARINE_MODEL_PATH = os.path.join(MODEL_DIR, "model_marine_env_real.pkl")
CATCH_MODEL_PATH = os.path.join(MODEL_DIR, "model_catch_forecast_real.pkl")

def get_prepared_data():
    df = create_dataset()

    # 注: 欠損値は残したまま返す（パラメータごとに実測データのみで学習するため）
    # 以前は全て dropna していたが、これだと実測データが少ないパラメータで学習できなかった
    return df

def train_marine_env_model(df):
    """
    【前段】海況予測モデル (Marine Environment Model)
    陸上の気象・潮汐データから、海の中の状況（水温、塩分、波高等）を予測する

    **重要な変更**: パラメータごとに実測データのみで個別に学習する
    - 以前はMultiOutputRegressorで全パラメータを同時学習していたが、
      補間データで学習していたため精度が崩壊していた
    - 新方式では、各パラメータの実測値がある行のみでモデルを学習する
    """
    print("\n" + "="*50)
    print("🌊 【前段】海況予測モデル (Marine Env Model) 学習開始...")
    print("  ⚠️  新方式: パラメータごとに実測データのみで個別学習")

    # --- 基本特徴量 (Inputs: 陸上・気象データ) ---
    base_features = [
        'avg_temp', 'max_temp', 'min_temp',
        'avg_wind_speed', 'max_wind_speed',
        'precipitation', 'precipitation_lag1', 'precipitation_lag2',
        'avg_wind_speed_lag1',
        'daylight_hours',
        'tide_level',
        'is_kuroshio_meander',
        'month_sin', 'month_cos'
    ]

    # --- 目的変数 (Outputs: 実測海況データ) ---
    targets = [
        'real_water_temp',
        'real_salinity',
        'real_do',
        'real_cod',
        'real_transparency',
        'real_wave_height',
        'wave_direction_dominant',
        'real_river_discharge'
    ]

    # パラメータごとのモデルを格納
    models = {}
    feature_sets = {}

    for target in targets:
        print(f"\n  📊 {target} のモデルを学習中...")

        # このターゲットのラグ特徴量
        lag_feature = f'{target}_lag1'

        # 特徴量セット
        features = base_features.copy()
        if lag_feature in df.columns:
            features.append(lag_feature)

        # このターゲットの実測値がある行のみを抽出
        valid_mask = df[target].notna()

        # ラグ特徴量も使う場合、それもNULLでない行のみ
        if lag_feature in features:
            valid_mask = valid_mask & df[lag_feature].notna()

        df_valid = df[valid_mask].copy()

        if len(df_valid) == 0:
            print(f"    ⚠️  実測データが0件のためスキップ")
            continue

        X = df_valid[features]
        y = df_valid[target]

        print(f"    実測データ数: {len(df_valid)}件 (全体の{100*len(df_valid)/len(df):.1f}%)")

        # 時系列を崩さずに分割
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, shuffle=False
        )

        # モデル学習
        model = LGBMRegressor(n_estimators=100, random_state=42, verbosity=-1)
        model.fit(X_train, y_train)

        # 評価
        pred_test = model.predict(X_test)
        r2 = r2_score(y_test, pred_test)
        rmse = np.sqrt(mean_squared_error(y_test, pred_test))
        print(f"    ✅ R2 = {r2:7.4f}, RMSE = {rmse:7.4f}")

        # モデルと特徴量セットを保存
        models[target] = model
        feature_sets[target] = features

        # 全データに対する予測値を生成（欠損値のある行も含めて）
        # 欠損がある行はNaNのまま
        df[f'pred_{target}'] = np.nan
        try:
            pred_all = model.predict(df[features].fillna(df[features].mean()))
            df[f'pred_{target}'] = pred_all
        except Exception as e:
            print(f"    ⚠️  予測値生成エラー: {e}")

    # モデル保存
    model_data = {
        "models": models,
        "feature_sets": feature_sets,
        "targets": list(models.keys())
    }
    joblib.dump(model_data, MARINE_MODEL_PATH)
    print(f"\n  💾 海況予測モデルを保存完了: {MARINE_MODEL_PATH}")
    print(f"  📊 学習完了したパラメータ数: {len(models)}/{len(targets)}")

    return models, df


def train_catch_forecast_model(df):
    """
    【後段】釣果予測モデル (Catch Forecast Model)
    陸上データ ＋ 「前段モデルが予測した海況データ」 から釣果件数を予測する
    """
    print("\n" + "="*50)
    print("🎣 【後段】釣果予測モデル (Catch Forecast Model) 学習開始...")
    
    # --- 特徴量 (Inputs: 陸上・気象データ + 【海況予測値】) ---
    features = [
        'avg_temp', 'max_temp', 'min_temp', 
        'avg_wind_speed', 'max_wind_speed', 
        'precipitation', 'precipitation_lag1', 'daylight_hours',
        'tide_level', 'is_kuroshio_meander',
        # 前段モデルの予測値を特徴量として使う
        'pred_real_water_temp', 
        'pred_real_salinity', 
        'pred_real_do', 
        'pred_real_transparency',
        'pred_real_wave_height',
        'pred_real_river_discharge',
        'month_sin', 'month_cos',
        'day_of_week', 'is_weekend'
    ]
    
    # --- 目的変数 (Output: 釣果件数) ---
    target = 'catch_count'
    
    X = df[features]
    y = df[target]
    
    print(f"  入力データ形状: X={X.shape}, y={y.shape}")
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    
    # 単一のターゲットなので普通のRegressor
    catch_model = LGBMRegressor(n_estimators=100, random_state=42, learning_rate=0.05, max_depth=7)
    catch_model.fit(X_train, y_train)
    
    # 評価
    pred_test = catch_model.predict(X_test)
    pred_test = np.maximum(0, pred_test) # 釣果はマイナスにならない
    
    r2 = r2_score(y_test, pred_test)
    rmse = np.sqrt(mean_squared_error(y_test, pred_test))
    
    print("  ✅ 学習完了! 釣果予測の精度:")
    print(f"    - Catch Count              : R2 = {r2:7.4f}, RMSE = {rmse:7.4f}")
    
    # 予測結果の分布を保存 (カレンダーUIでのパーセンタイル計算用)
    pred_all = np.maximum(0, catch_model.predict(X))
    score_distribution = np.sort(pred_all)
    
    # 特徴量重要度の表示
    importances = catch_model.feature_importances_
    indices = np.argsort(importances)[::-1]
    print("\n  🌟 特徴量重要度 Top 10:")
    for f in range(min(10, len(features))):
        print(f"    {f+1}. {features[indices[f]]:<25} ({importances[indices[f]]:.4f})")

    # モデル保存
    model_data = {
        "model": catch_model,
        "features": features,
        "score_distribution": score_distribution
    }
    joblib.dump(model_data, CATCH_MODEL_PATH)
    print(f"  💾 釣果予測モデルを保存完了: {CATCH_MODEL_PATH}")
    
    return catch_model

def main():
    print("🚀 2段階AI（海況予測 ＋ 釣果予測）実測データ統合学習パイプライン起動")
    df = get_prepared_data()
    
    # 1. 前段モデルの学習 (海況の予測)
    _, df_with_preds = train_marine_env_model(df)
    
    # 2. 後段モデルの学習 (釣果の予測)
    train_catch_forecast_model(df_with_preds)
    
    print("\n🎉 全AIモデルの学習・保存が正常に完了しました！")

if __name__ == "__main__":
    main()
