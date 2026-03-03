"""
魚種別釣果予測モデルの学習スクリプト
既存の train_real_marine.py を変更せず、追加で魚種特化モデルを作る。
海況モデル（model_marine_env_real.pkl）は既存のものをそのまま使う。

使い方:
  python train_species.py アジ
"""
import argparse
import os
import sqlite3

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

# 既存のユーティリティを再利用
from train_real_marine import safe_impute

ML_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(ML_DIR))
DB_PATH = os.path.join(BASE_DIR, 'data', 'fishing_forecast.db')
MARINE_MODEL_PATH = os.path.join(ML_DIR, "model_marine_env_real.pkl")

# 魚種名寄せマッピング (DB の species カラムに対する LIKE 条件)
SPECIES_ALIASES = {
    'アジ': ['アジ'],
    'スズキ': ['スズキ', 'シーバス', 'フッコ', 'セイゴ'],
    'カサゴ': ['カサゴ'],
    'クロダイ': ['クロダイ', 'チヌ'],
    'シロギス': ['シロギス', 'キス'],
    'カワハギ': ['カワハギ'],
    'サバ': ['サバ'],
    'メバル': ['メバル'],
    'メジナ': ['メジナ'],
    'アオリイカ': ['アオリイカ'],
}


def fetch_species_catch(species_name):
    """
    指定魚種の日別CPUE（1人あたり平均釣果数）をDBから取得する。
    施設データのみ使用: アジ釣果合計 ÷ visitors（来場者数）= 正確なCPUE
    """
    aliases = SPECIES_ALIASES.get(species_name, [species_name])
    like_conditions = " OR ".join([f"species LIKE '%{a}%'" for a in aliases])

    conn = sqlite3.connect(DB_PATH)
    query = f"""
    SELECT fl.date, fl.facility, fl.visitors,
           SUM(COALESCE(fc.count, 1)) as total_catch,
           SUM(COALESCE(fc.count, 1)) * 1.0 / fl.visitors as cpue
    FROM facility_catches fc
    JOIN facility_logs fl ON fc.log_id = fl.id
    WHERE ({like_conditions})
    AND fl.visitors > 0
    GROUP BY fl.date, fl.facility
    """
    df_raw = pd.read_sql_query(query, conn)
    conn.close()

    if df_raw.empty:
        print(f"  ⚠️ {species_name} の施設データが見つかりません")
        return pd.DataFrame(columns=['species_catch'])

    df_raw['date'] = pd.to_datetime(df_raw['date'])
    # 日付別に施設の平均CPUEを取る
    df_result = df_raw.groupby('date')['cpue'].mean().reset_index()
    df_result.columns = ['date', 'species_catch']
    df_result.set_index('date', inplace=True)

    print(f"  📊 施設データ: {len(df_raw)}件 ({df_raw['facility'].nunique()}施設)")
    print(f"  📊 CPUE: 平均={df_result['species_catch'].mean():.2f}匹/人, 中央値={df_result['species_catch'].median():.2f}, 最大={df_result['species_catch'].max():.2f}")
    return df_result


def build_species_dataset(species_name):
    """
    既存の create_dataset() で作ったベースデータに、
    魚種別の釣果カラムを追加して返す。
    """
    from dataset_real_marine import create_dataset
    print(f"📦 ベースデータセット取得中...")
    df = create_dataset().sort_index()

    print(f"🐟 {species_name} の釣果データを取得中...")
    df_species = fetch_species_catch(species_name)
    df = df.merge(df_species, left_index=True, right_index=True, how='left')
    # 改善 #3: fillna(0) を廃止。報告がない日はNaNのまま残す。
    # 後続の学習で dropna して、実際に報告がある日のみ学習対象にする。

    print(f"  → {species_name} の釣果がある日数: {(df['species_catch'] > 0).sum()}")
    return df


def add_marine_predictions(df):
    """
    既存の海況モデル（model_marine_env_real.pkl）を使って、
    pred_real_water_temp 等の海況予測カラムを追加する。
    train_real_marine.py の後段処理と同じロジック。
    """
    if not os.path.exists(MARINE_MODEL_PATH):
        print("⚠️ 海況モデルが見つかりません。先に train_real_marine.py を実行してください。")
        return df

    marine_models = joblib.load(MARINE_MODEL_PATH)
    targets = [
        'real_water_temp', 'final_salinity', 'real_do',
        'real_cod', 'real_transparency', 'real_wave_height',
        'wave_direction_dominant', 'real_river_discharge',
        'final_ssh', 'final_current_u', 'final_current_v'
    ]

    for target in targets:
        pred_col = f'pred_{target}'
        if target in marine_models:
            m_info = marine_models[target]
            X = safe_impute(df[m_info["features"]], is_train=False, train_means=m_info["train_means"])
            df[pred_col] = m_info["model"].predict(X)
        else:
            df[pred_col] = 0.5
    return df


def train_species_model(species_name):
    """
    メイン: 魚種別モデルの学習
    """
    print(f"\n{'='*50}")
    print(f"🎣 魚種別モデル学習: {species_name}")
    print(f"{'='*50}")

    # 1. データセット構築
    df = build_species_dataset(species_name)
    df = add_marine_predictions(df)

    # 改善 #3: 釣果データがある行のみ使用（報告なし=NaN を学習に使わない）
    df = df.dropna(subset=['species_catch'])
    print(f"  📊 {species_name} の釣果データがある日数: {len(df)}")

    # 2. 特徴量とターゲット
    features = [
        'avg_temp', 'max_temp', 'min_temp',
        'avg_wind_speed', 'max_wind_speed',
        'precipitation', 'precipitation_lag1', 'daylight_hours',
        'tide_level', 'is_kuroshio_meander',
        'copernicus_chlorophyll', 'copernicus_oxygen',
        'pred_real_water_temp', 'pred_final_salinity', 'pred_real_do',
        'pred_real_transparency', 'pred_real_wave_height', 'pred_real_river_discharge',
        'pred_final_ssh', 'pred_final_current_u', 'pred_final_current_v',
        'month_sin', 'month_cos', 'day_of_week', 'is_weekend'
    ]
    target = 'species_catch'

    # 3. 時系列分割
    split_idx = int(len(df) * 0.8)
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    X_train, train_means = safe_impute(train_df[features], is_train=True)
    y_train = train_df[target]
    X_test = safe_impute(test_df[features], is_train=False, train_means=train_means)
    y_test = test_df[target]

    # 4. 交差検証
    tscv = TimeSeriesSplit(n_splits=5)
    cv_r2, cv_rmse = [], []
    for tr_idx, te_idx in tscv.split(train_df):
        X_tr, means = safe_impute(train_df.iloc[tr_idx][features], is_train=True)
        X_te = safe_impute(train_df.iloc[te_idx][features], is_train=False, train_means=means)
        y_tr = train_df.iloc[tr_idx][target]
        y_te = train_df.iloc[te_idx][target]

        m = LGBMRegressor(n_estimators=100, random_state=42, learning_rate=0.05, max_depth=7, verbosity=-1)
        m.fit(X_tr, y_tr)
        p = np.maximum(0, m.predict(X_te))
        cv_r2.append(r2_score(y_te, p))
        cv_rmse.append(np.sqrt(mean_squared_error(y_te, p)))

    print(f"  🔍 CV R2: {np.mean(cv_r2):.4f} ± {np.std(cv_r2):.4f}")
    print(f"  🔍 CV RMSE: {np.mean(cv_rmse):.4f} ± {np.std(cv_rmse):.4f}")

    # 5. 本番モデル学習
    model = LGBMRegressor(n_estimators=100, random_state=42, learning_rate=0.05, max_depth=7, verbosity=-1)
    model.fit(X_train, y_train)

    # 6. Hold-out 評価
    pred_test = np.maximum(0, model.predict(X_test))
    r2 = r2_score(y_test, pred_test)
    rmse = np.sqrt(mean_squared_error(y_test, pred_test))
    avg_catch = y_test.mean()
    print(f"  ✅ Hold-out R2 = {r2:.4f}, RMSE = {rmse:.4f}")
    print(f"  📊 テスト期間の平均{species_name}釣果: {avg_catch:.2f}")

    # 7. スコア分布の保存（パーセンタイル用）
    pred_all = np.maximum(0, model.predict(safe_impute(df[features], is_train=False, train_means=train_means)))
    score_distribution = np.sort(pred_all)

    # 8. 保存
    model_data = {
        "model": model,
        "features": features,
        "score_distribution": score_distribution,
        "train_means": train_means,
        "species": species_name
    }
    out_path = os.path.join(ML_DIR, f"model_catch_forecast_{species_name}.pkl")
    joblib.dump(model_data, out_path)
    print(f"  💾 保存完了: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="魚種別釣果予測モデルの学習")
    parser.add_argument("species", type=str, help="対象魚種名（例: アジ）")
    args = parser.parse_args()

    if args.species not in SPECIES_ALIASES:
        print(f"⚠️ 未対応の魚種: {args.species}")
        print(f"   対応魚種: {', '.join(SPECIES_ALIASES.keys())}")
    else:
        train_species_model(args.species)
