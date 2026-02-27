import argparse
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.multioutput import MultiOutputRegressor
from sklearn.ensemble import RandomForestRegressor
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split, TimeSeriesSplit
# --- Utilities ---
from dataset_real_marine import create_dataset

def safe_impute(df, is_train=True, train_means=None):
    """
    時系列データのリークを防ぎながら補完を行う
    """
    df = df.copy()
    
    # 1. 前方向埋め (過去の値を引き継ぐ)
    df = df.ffill()
    
    # 2. それでも NaN が残る場合 (データの最初の方など) は、
    # Train の場合は自身の平均、Test の場合は Train の平均で埋める
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

def train_marine_env_model(df):
    """
    【前段】海況予測モデル (Marine Environment Model) 改良版
    各海況パラメータごとに、実測値があるデータのみを使って個別にモデルを学習する。
    これによって、粗い実測データを最大限に活用し、かつ Leakage を防ぐ。
    """
    print("\n" + "="*50)
    print("🌊 【前段】海況予測モデル (Marine Env Model) 個別学習開始...")
    
    # 共通特徴量
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
    
    targets = [
        'real_water_temp', 'real_salinity', 'real_do', 
        'real_cod', 'real_transparency', 'real_wave_height', 
        'wave_direction_dominant', 'real_river_discharge'
    ]
    
    models = {}
    
    # 時系列で分割 (80:20)
    split_idx = int(len(df) * 0.8)
    train_df_raw = df.iloc[:split_idx]
    test_df_raw = df.iloc[split_idx:]
    
    print(f"  データ分割: Train={len(train_df_raw)}, Test={len(test_df_raw)}")

    for target in targets:
        print(f"  -> {target} のモデルを構築中...")
        
        # ラグ変数はTrain-Serving Skewを引き起こすため廃止 (Issue #40)
        target_features = base_features.copy()
        
        # 1. 学習データの準備: このターゲットの実測値がある行だけを抽出
        # 他の行は未来推測には使えない（あるいは補完によるリークの原因になる）
        train_data = train_df_raw.dropna(subset=[target])
        if len(train_data) < 50:
            print(f"    ⚠️ データ不足 ({len(train_data)}件)。スキップします。")
            continue
            
        # 学習データの補完 (ラグ変数の NaN などを埋める)
        X_train_raw = train_data[target_features]
        y_train = train_data[target]
        X_train, train_means = safe_impute(X_train_raw, is_train=True)
        
        # 2. 交差検証 (TimeSeriesSplit) による評価
        tscv = TimeSeriesSplit(n_splits=5)
        cv_r2 = []
        cv_rmse = []

        # NaNが除去された train_data のみでCVを行う
        X_data_cv = train_data[target_features].reset_index(drop=True)
        y_data_cv = train_data[target].reset_index(drop=True)

        for train_index, test_index in tscv.split(X_data_cv):
            X_tr_raw, X_te_raw = X_data_cv.iloc[train_index], X_data_cv.iloc[test_index]
            y_tr, y_te = y_data_cv.iloc[train_index], y_data_cv.iloc[test_index]
            
            X_tr, means = safe_impute(X_tr_raw, is_train=True)
            X_te = safe_impute(X_te_raw, is_train=False, train_means=means)
            
            cv_model = LGBMRegressor(n_estimators=100, random_state=42, verbosity=-1)
            cv_model.fit(X_tr, y_tr)
            
            p_te = cv_model.predict(X_te)
            cv_r2.append(r2_score(y_te, p_te))
            cv_rmse.append(np.sqrt(mean_squared_error(y_te, p_te)))
            
        print(f"    --> CV R2: {np.mean(cv_r2):.4f} ± {np.std(cv_r2):.4f}, RMSE: {np.mean(cv_rmse):.4f} ± {np.std(cv_rmse):.4f}")

        # 3. 本番モデルの学習 (Hold-out Testで最終確認)
        model = LGBMRegressor(n_estimators=100, random_state=42, importance_type='gain', verbosity=-1)
        model.fit(X_train, y_train)
        
        # 4. ホールドアウトデータでの評価
        X_test_all = safe_impute(test_df_raw[target_features], is_train=False, train_means=train_means)
        y_test_all = test_df_raw[target]
        
        preds_test = model.predict(X_test_all)
        
        # 実測がある部分のみで精度計算
        mask = ~y_test_all.isna()
        if mask.any():
            r2 = r2_score(y_test_all[mask], preds_test[mask])
            rmse = np.sqrt(mean_squared_error(y_test_all[mask], preds_test[mask]))
            print(f"    ✅ Hold-out R2 = {r2:7.4f}, RMSE = {rmse:7.4f} (実測数: {mask.sum()})")
        
        models[target] = {
            "model": model,
            "features": target_features,
            "train_means": train_means
        }
        
    # モデルの保存
    joblib.dump(models, MARINE_MODEL_PATH)
    print(f"  💾 個別海況予測モデルを保存完了: {MARINE_MODEL_PATH}")
    
    # 釣果モデル学習用に、全期間の「予測海況」を埋める
    # ここでも Data Leakage が起きないよう、各時点での予測値のみを使用
    for target in targets:
        pred_col = f'pred_{target}'
        if target in models:
            m_info = models[target]
            X_all = safe_impute(df[m_info["features"]], is_train=False, train_means=m_info["train_means"])
            df[pred_col] = m_info["model"].predict(X_all)
        else:
            # モデルが作れなかった場合は、安全なデフォルト値（0.5など）で埋める
            # TODO: 予測値の誤差伝播の問題（Issue #41）に関連。将来的に改善予定。
            print(f"    ⚠️ 警告: {target} のモデルがないため、デフォルト値 0.5 で埋めます。 (Issue #41 関連)")
            df[pred_col] = 0.5
            
    return models, df


def train_catch_forecast_model(df):
    """
    【後段】釣果予測モデル
    """
    print("\n" + "="*50)
    print("🎣 【後段】釣果予測モデル (Catch Forecast Model) 学習開始...")
    
    features = [
        'avg_temp', 'max_temp', 'min_temp', 
        'avg_wind_speed', 'max_wind_speed', 
        'precipitation', 'precipitation_lag1', 'daylight_hours',
        'tide_level', 'is_kuroshio_meander',
        'pred_real_water_temp', 'pred_real_salinity', 'pred_real_do', 
        'pred_real_transparency', 'pred_real_wave_height', 'pred_real_river_discharge',
        'month_sin', 'month_cos', 'day_of_week', 'is_weekend'
    ]
    target = 'catch_count'
    
    # 時系列分割
    split_idx = int(len(df) * 0.8)
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]
    
    X_train_raw = train_df[features]
    y_train = train_df[target]
    X_test_raw = test_df[features]
    y_test = test_df[target]
    
    # 補完 (釣果モデル側でも念のため)
    X_train, train_means = safe_impute(X_train_raw, is_train=True)
    X_test = safe_impute(X_test_raw, is_train=False, train_means=train_means)
    
    # 1. 交差検証 (TimeSeriesSplit) による評価
    tscv = TimeSeriesSplit(n_splits=5)
    cv_r2 = []
    cv_rmse = []
    
    # NaNが含まれない df に対してCVを実行
    for train_index, test_index in tscv.split(train_df):
        X_tr_raw = train_df.iloc[train_index][features]
        X_te_raw = train_df.iloc[test_index][features]
        # target は catch_count
        y_tr = train_df.iloc[train_index][target]
        y_te = train_df.iloc[test_index][target]
        
        X_tr, means = safe_impute(X_tr_raw, is_train=True)
        X_te = safe_impute(X_te_raw, is_train=False, train_means=means)
        
        cv_model = LGBMRegressor(n_estimators=100, random_state=42, learning_rate=0.05, max_depth=7, verbosity=-1)
        cv_model.fit(X_tr, y_tr)
        
        p_te = np.maximum(0, cv_model.predict(X_te))
        cv_r2.append(r2_score(y_te, p_te))
        cv_rmse.append(np.sqrt(mean_squared_error(y_te, p_te)))

    print(f"  🔍 CV R2: {np.mean(cv_r2):.4f} ± {np.std(cv_r2):.4f}, RMSE: {np.mean(cv_rmse):.4f} ± {np.std(cv_rmse):.4f}")

    # 2. 本番モデルの学習 (Hold-out Testで最終確認)
    catch_model = LGBMRegressor(n_estimators=100, random_state=42, learning_rate=0.05, max_depth=7, verbosity=-1)
    catch_model.fit(X_train, y_train)
    
    # 3. ホールドアウトデータでの評価
    pred_test = np.maximum(0, catch_model.predict(X_test))
    r2 = r2_score(y_test, pred_test)
    rmse = np.sqrt(mean_squared_error(y_test, pred_test))
    
    print(f"  ✅ Hold-out R2 = {r2:7.4f}, RMSE = {rmse:7.4f}")
    
    # 予測分布の保存
    pred_all = np.maximum(0, catch_model.predict(safe_impute(df[features], is_train=False, train_means=train_means)))
    score_distribution = np.sort(pred_all)
    
    model_data = {
        "model": catch_model,
        "features": features,
        "score_distribution": score_distribution,
        "train_means": train_means
    }
    joblib.dump(model_data, CATCH_MODEL_PATH)
    return catch_model

# --- Dataset Loading ---
from dataset_real_marine import create_dataset

MODEL_DIR = os.path.dirname(__file__)
MARINE_MODEL_PATH = os.path.join(MODEL_DIR, "model_marine_env_real.pkl")
CATCH_MODEL_PATH = os.path.join(MODEL_DIR, "model_catch_forecast_real.pkl")

def main():
    print("🚀 Data Leakage 対策版 学習パイプライン起動")
    # 1. Rawデータ取得 (補完なし)
    df = create_dataset()
    
    # 時系列分割のため、念のため日付順にソート（インデックスがDatetimeIndexであることを前提）
    df = df.sort_index()
    
    # 2. 海況モデル学習 (個別・分割後補完)
    _, df_with_preds = train_marine_env_model(df)
    
    # 3. 釣果モデル学習
    train_catch_forecast_model(df_with_preds)
    
    print("\n🎉 全AIモデルの学習・保存が正常に完了しました！ (Issue #39 対応)")

if __name__ == "__main__":
    main()
