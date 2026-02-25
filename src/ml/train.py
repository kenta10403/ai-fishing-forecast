import os
import argparse
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from dataset import load_data, preprocess_data

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")

def train_model(include_files=None, exclude_files=None, target_species=None):
    print("データの読み込み中...")
    df_raw = load_data(include_files, exclude_files, target_species)
    if df_raw.empty:
        print("エラー: 有効なデータがロードできませんでした。")
        return

    print("データの前処理中...")
    X, y = preprocess_data(df_raw)
    
    print(f"X shape: {X.shape}, y shape: {y.shape}")
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("モデルの学習中 (RandomForestRegressor)...")
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    predict_train = model.predict(X_train)
    mse = mean_squared_error(y_train, predict_train)
    r2 = r2_score(y_train, predict_train)
    
    print(f"学習完了!")
    print(f" - Train Mean Squared Error (MSE): {mse:.4f}")
    print(f" - Train R2 Score: {r2:.4f}")
    
    import numpy as np
    
    # 100点満点評価（爆釣指数）算出のための分布データを保存
    score_distribution = np.sort(y_train.values)
    
    # 時期(period_of_year: 1〜36)ごとの過去の平均CPUEを計算・保存
    # テストデータを含めた全データ(df_rawの加工後)の X と y から集計する
    period_avg_dict = {}
    for p in range(1, 37):
        mask = X['period_of_year'] == p
        if mask.sum() > 0:
            period_avg_dict[p] = float(np.mean(y[mask]))
        else:
            # その時期のデータがない場合は全体の平均を設定
            period_avg_dict[p] = float(np.mean(y))
    
    # save model and feature names (columns)
    model_data = {
        "model": model,
        "features": X.columns.tolist(),
        "score_distribution": score_distribution,
        "period_averages": period_avg_dict
    }
    
    # ターゲット魚種に応じた固有のファイル名で保存
    if target_species:
        model_filename = f"model_cpue_{target_species}.pkl"
    else:
        model_filename = "model_cpue_total.pkl"
        
    model_path = os.path.join(os.path.dirname(__file__), model_filename)
        
    joblib.dump(model_data, model_path)
    print(f"モデルを {model_path} に保存しました。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="釣果予測モデルの学習スクリプト")
    parser.add_argument("--include", nargs="+", help="対象JSONファイル（例: daikoku_2024_to_present.json）")
    parser.add_argument("--target", type=str, help="対象魚種（例: アジ）。未指定の場合は総釣果量を予測")
    
    args = parser.parse_args()
    train_model(include_files=args.include, target_species=args.target)
