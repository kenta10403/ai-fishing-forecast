import argparse
import os

import joblib
from dataset_b import TARGET_SPECIES_LIST, load_data_b, preprocess_data_b
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_b.pkl")

def train_model_b(include_files=None, exclude_files=None):
    print("パターンB: 複数魚種データの読み込み中...")
    df_raw = load_data_b(include_files, exclude_files)
    if df_raw.empty:
        print("エラー: 有効なデータがロードできませんでした。")
        return

    print("パターンB: データの前処理中...")
    X, Y = preprocess_data_b(df_raw)

    print(f"X shape: {X.shape}, Y shape: {Y.shape}")

    X_train, X_test, Y_train, Y_test = train_test_split(X, Y, test_size=0.2, random_state=42)

    # RandomForestRegressorは元々Multi-output Regressionをサポートしているためそのまま使用可能
    print("モデルの学習中 (Multi-Output RandomForestRegressor)...")
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, Y_train)

    # 簡単な評価スコア
    score = model.score(X_test, Y_test)
    print(f"学習完了! - 全体 R2 Score: {score:.2f}")

    model_data = {
        "model": model,
        "features": X.columns.tolist(),
        "targets": TARGET_SPECIES_LIST
    }

    joblib.dump(model_data, MODEL_PATH)
    print(f"マルチターゲットモデルを {MODEL_PATH} に保存しました。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="釣れそうな魚ランキング予測モデルの学習")
    parser.add_argument("--include", nargs="+", help="対象JSONファイル（例: daikoku_2024_to_present.json）")

    args = parser.parse_args()
    train_model_b(include_files=args.include)
