import os
import argparse
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
import numpy as np

from dataset_d import load_trend_data, preprocess_trend_data

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
    
    print(f"学習完了!")
    print(f" - Test MSE: {mse:.4f}")
    print(f" - Test R2 Score: {r2:.4f} (※バイアスの強いデータなので参考値)")
    
    # トレンド指数の規模感（パーセンタイル）を出すための分布を保存
    score_distribution = np.sort(y_train.values)
    
    # 使用された特徴量のカラムと、ユニークな魚種リスト・エリアリストも記録しておく
    model_data = {
        "model": model,
        "features": X.columns.tolist(),
        "score_distribution": score_distribution,
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
