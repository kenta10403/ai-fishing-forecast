from dataset_real_marine import create_dataset as get_prepared_data
from sklearn.multioutput import MultiOutputRegressor
from lightgbm import LGBMRegressor
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split
import numpy as np
import pandas as pd

def run_multi_test(n_iterations=10):
    print(f"🕵️  R2=0.98の真実を暴く！ {n_iterations}回連続テスト開始...")
    df = get_prepared_data()
    
    features = [
        'avg_temp', 'max_temp', 'min_temp', 
        'avg_wind_speed', 'max_wind_speed', 
        'precipitation', 'precipitation_lag1', 'precipitation_lag2',
        'avg_wind_speed_lag1', 'daylight_hours', 'tide_level', 'is_kuroshio_meander',
        'real_water_temp_lag1', 'real_salinity_lag1', 'real_do_lag1',
        'real_cod_lag1', 'real_transparency_lag1', 
        'real_wave_height_lag1', 'real_river_discharge_lag1'
    ]
    targets = ['real_water_temp', 'real_salinity', 'real_transparency', 'real_wave_height']
    
    X = df[features]
    y = df[targets]
    
    # ターゲットにNaNがある行を除去 (MultiOutputRegressorはNaNを許容しないため)
    valid_mask = y.notna().all(axis=1)
    X = X[valid_mask]
    y = y[valid_mask]
    
    if len(X) < 10:
        print("⚠️ 有効なデータが少なすぎて評価できません")
        return

    results = {t: [] for t in targets}
    
    for i in range(n_iterations):
        # 毎回ランダムシードを変えて分割
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=i*42)
        
        model = MultiOutputRegressor(LGBMRegressor(n_estimators=100, verbosity=-1))
        model.fit(X_train, y_train)
        
        preds = model.predict(X_test)
        
        for idx, target_name in enumerate(targets):
            r2 = r2_score(y_test.iloc[:, idx], preds[:, idx])
            results[target_name].append(r2)
            
        print(f"  Iteration {i+1}/10: WaterTemp R2 = {results['real_water_temp'][-1]:.4f}")

    print("\n" + "="*50)
    print("📊 10回テスト平均結果 (R2 Score)")
    for target_name, scores in results.items():
        avg = np.mean(scores)
        std = np.std(scores)
        print(f"- {target_name:<20}: 平均 {avg:.4f} (±{std:.4f})")
    print("="*50)

if __name__ == "__main__":
    run_multi_test()
