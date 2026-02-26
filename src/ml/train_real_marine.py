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
    
    # 欠損値を含む行をドロップ（補完済みのはずだが念の為）
    df = df.dropna()
    return df

def train_marine_env_model(df):
    """
    【前段】海況予測モデル (Marine Environment Model)
    陸上の気象・潮汐データから、海の中の状況（水温、塩分、波高等）を予測する
    """
    print("\n" + "="*50)
    print("🌊 【前段】海況予測モデル (Marine Env Model) 学習開始...")
    
    # --- 特徴量 (Inputs: 陸上・気象データ) ---
    features = [
        'avg_temp', 'max_temp', 'min_temp', 
        'avg_wind_speed', 'max_wind_speed', 
        'precipitation', 'precipitation_lag1', 'precipitation_lag2',
        'avg_wind_speed_lag1',
        'daylight_hours',
        'tide_level',
        'is_kuroshio_meander'
    ]
    
    # 昨日までの海況 (自己回帰特徴量) を持たせることで予測精度アップ
    lag_features = [
        'real_water_temp_lag1', 'real_salinity_lag1', 'real_do_lag1',
        'real_cod_lag1', 'real_transparency_lag1', 
        'real_wave_height_lag1', 'real_river_discharge_lag1'
    ]
    features.extend(lag_features)
    
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
    
    X = df[features]
    y = df[targets]
    
    print(f"  入力データ形状: X={X.shape}, y={y.shape}")
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=False) # 時系列を崩さないようにshuffle=Falseがいいが、とりあえずベースライン
    
    # MultiOutputRegressor を使って複数の目的変数を同時に予測
    base_model = LGBMRegressor(n_estimators=100, random_state=42)
    marine_model = MultiOutputRegressor(base_model)
    
    marine_model.fit(X_train, y_train)
    
    # 評価
    pred_test = marine_model.predict(X_test)
    
    print("  ✅ 学習完了! 各海況パラメータの R2スコア:")
    for i, target_name in enumerate(targets):
        r2 = r2_score(y_test.iloc[:, i], pred_test[:, i])
        rmse = np.sqrt(mean_squared_error(y_test.iloc[:, i], pred_test[:, i]))
        print(f"    - {target_name:<25}: R2 = {r2:7.4f}, RMSE = {rmse:7.4f}")
        
    # モデル保存
    model_data = {
        "model": marine_model,
        "features": features,
        "targets": targets
    }
    joblib.dump(model_data, MARINE_MODEL_PATH)
    print(f"  💾 海況予測モデルを保存完了: {MARINE_MODEL_PATH}")
    
    # 釣果モデル学習用に、テスト期間含めた全期間の「予測海況」を出力してdfにつなげる
    pred_all = marine_model.predict(X)
    for i, target_name in enumerate(targets):
        df[f'pred_{target_name}'] = pred_all[:, i]
        
    return marine_model, df


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
        'pred_real_river_discharge'
    ]
    
    # --- 目的変数 (Output: 釣果件数) ---
    target = 'catch_count'
    
    X = df[features]
    y = df[target]
    
    print(f"  入力データ形状: X={X.shape}, y={y.shape}")
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
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
