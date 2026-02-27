import pandas as pd
import numpy as np
import os
import joblib
from dataset_real_marine import create_dataset
import matplotlib.pyplot as plt
import seaborn as sns

def analyze_fishing_factors():
    print("📋 釣果影響因子の詳細分析を開始します...")
    
    # データセット取得
    df = create_dataset()
    
    # ターゲット: 釣果件数 (catch_count)
    target = 'catch_count'
    
    # 分析対象の主要因子
    factors = [
        'avg_temp', 'avg_wind_speed', 'precipitation', 'daylight_hours',
        'tide_level', 'real_water_temp', 'real_salinity', 'real_do', 
        'real_transparency', 'real_wave_height', 'real_river_discharge',
        'day_of_week', 'is_weekend'
    ]
    
    # 1. 相関係数の算出 (Pearson Correlation)
    correlations = df[factors + [target]].corr()[target].sort_values(ascending=False)
    
    print("\n📈 釣果数との相関関係 (TOP順):")
    print("-" * 50)
    for factor, value in correlations.items():
        if factor == target: continue
        desc = "正の相関 (高いと釣れる)" if value > 0 else "負の相関 (低いと釣れる)"
        print(f"  {factor:<25} : {value:>7.4f} ({desc})")
    
    # 2. 特徴量重要度の詳細 (LGBMのモデルから取得)
    CATCH_MODEL_PATH = "src/ml/model_catch_forecast_real.pkl"
    if os.path.exists(CATCH_MODEL_PATH):
        model_data = joblib.load(CATCH_MODEL_PATH)
        model = model_data['model']
        feature_importances = pd.Series(model.feature_importances_, index=model_data['features']).sort_values(ascending=False)
        
        print("\n🧠 AIモデルによる重要度ランキング (寄与度順):")
        print("-" * 50)
        total_importance = feature_importances.sum()
        for feature, value in feature_importances.items():
            percentage = (value / total_importance) * 100
            print(f"  {feature:<25} : {value:>7.1f} ({percentage:>5.1f}%)")
    
    # 3. 具体的な「釣り人のための知見」まとめ
    print("\n💡 データから導き出された「釣れる条件」の要約:")
    print("-" * 50)
    
    # 水温の傾向
    if correlations['real_water_temp'] > 0:
        print("✅ 水温: 水温が上がると全体の釣果が増える傾向。プランクトンの増殖が影響か。")
    
    # 透明度（濁り）の傾向
    if correlations['real_transparency'] < 0:
        print("✅ 濁り: 透明度が低い（＝適度に濁っている）ほうが釣果が良い傾向。魚の警戒心が薄れるため。")
    else:
        print("✅ 透明度: 澄んでいるほうが釣果が良い傾向。視覚で追う魚が多い可能性。")
        
    # 波高の傾向
    if correlations['real_wave_height'] < 0:
        print("✅ 波高: 波が穏やかなほうが釣果が伸びる。荒れると底荒れして魚が避難するか、釣り人が減る影響。")

    # 河川流量の傾向
    if correlations['real_river_discharge'] > 0:
        print("✅ 流量: 川からの流れ込みが増えると（水が動くと）反応が良い傾向。")
    else:
        print("✅ 流量: 流量が安定しているほうが釣果が安定。急な増水はマイナス。")

if __name__ == "__main__":
    analyze_fishing_factors()
