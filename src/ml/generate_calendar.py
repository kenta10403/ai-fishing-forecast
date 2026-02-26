import json
import os
import urllib.request
from datetime import datetime, timedelta

import joblib
import numpy as np
import pandas as pd
import scipy.stats as stats

# -- Model Paths --
ML_DIR = os.path.dirname(__file__)
MARINE_MODEL_PATH = os.path.join(ML_DIR, "model_marine_env_real.pkl")
CATCH_MODEL_PATH = os.path.join(ML_DIR, "model_catch_forecast_real.pkl")

# -- Coordinates (Tokyo Bay / Yokohama) --
LAT = 35.44
LON = 139.64

def get_tide_level(d):
    """
    月齢から潮回りを数値化 (0:若潮 ... 4:大潮)
    """
    ref = datetime(2026, 2, 17, 16, 1) # 新月参考
    diff = (d - ref).total_seconds() / (24 * 3600)
    age = diff % 29.53059
    
    if age < 2.5 or (age >= 13.7 and age < 17.5) or age >= 28.2: return 4 # 大潮
    if (age >= 2.5 and age < 5.5) or (age >= 10.5 and age < 13.7) or (age >= 17.5 and age < 20.5) or (age >= 25.5 and age < 28.2): return 3 # 中潮
    if (age >= 5.5 and age < 8.5) or (age >= 20.5 and age < 23.5): return 2 # 小潮
    if (age >= 8.5 and age < 9.5) or (age >= 23.5 and age < 24.5): return 1 # 長潮
    return 0 # 若潮

def fetch_openmeteo_all(start_date, end_date):
    """
    Open-Meteoの各種APIから、推論に必要な気象・海況予報を一括取得
    """
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    data_map = {}
    dates = pd.date_range(start_date, end_date)
    for d in dates:
        data_map[d.strftime("%Y-%m-%d")] = {}

    # 1. Weather Forecast (Temp, Wind, Rain)
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,shortwave_radiation_sum&timezone=Asia%2FTokyo&start_date={start_str}&end_date={end_str}"
    try:
        with urllib.request.urlopen(url) as res:
            d_json = json.loads(res.read().decode())
            daily = d_json['daily']
            for i, t in enumerate(daily['time']):
                if t in data_map:
                    data_map[t]['max_temp'] = daily['temperature_2m_max'][i]
                    data_map[t]['min_temp'] = daily['temperature_2m_min'][i]
                    data_map[t]['avg_temp'] = (daily['temperature_2m_max'][i] + daily['temperature_2m_min'][i]) / 2
                    data_map[t]['precipitation'] = daily['precipitation_sum'][i]
                    data_map[t]['max_wind_speed'] = daily['windspeed_10m_max'][i] / 3.6 # km/h to m/s
                    data_map[t]['avg_wind_speed'] = data_map[t]['max_wind_speed'] * 0.7 # 簡易計算
                    # Radiation to Daylight Hours approx
                    data_map[t]['daylight_hours'] = min(12, daily['shortwave_radiation_sum'][i] / 5) 
    except Exception as e: print(f"Weather API Error: {e}")

    # 2. Marine Forecast (Wave)
    url = f"https://marine-api.open-meteo.com/v1/marine?latitude={LAT}&longitude={LON}&daily=wave_height_max&timezone=Asia%2FTokyo&start_date={start_str}&end_date={end_str}"
    try:
        with urllib.request.urlopen(url) as res:
            d_json = json.loads(res.read().decode())
            daily = d_json['daily']
            for i, t in enumerate(daily['time']):
                if t in data_map:
                    data_map[t]['wave_height'] = daily['wave_height_max'][i]
    except Exception as e: print(f"Marine API Error: {e}")

    # 3. Flood Forecast (River Discharge)
    url = f"https://flood-api.open-meteo.com/v1/flood?latitude={LAT}&longitude={LON}&daily=river_discharge&timezone=Asia%2FTokyo&start_date={start_str}&end_date={end_str}"
    try:
        with urllib.request.urlopen(url) as res:
            d_json = json.loads(res.read().decode())
            daily = d_json['daily']
            for i, t in enumerate(daily['time']):
                if t in data_map:
                    data_map[t]['river_discharge'] = daily['river_discharge'][i]
    except Exception as e: print(f"Flood API Error: {e}")

    return data_map

def generate_ai_calendar(num_days=14):
    """
    2段階AIモデルを使って最新の釣果予測カレンダーを生成
    """
    print("🚀 2段階AI推論パイプライン実行中...")
    
    if not (os.path.exists(MARINE_MODEL_PATH) and os.path.exists(CATCH_MODEL_PATH)):
        print("Error: AIモデルが見つかりません。train_real_marine.pyを先に実行してください。")
        return

    marine_data = joblib.load(MARINE_MODEL_PATH)
    catch_data = joblib.load(CATCH_MODEL_PATH)
    
    marine_model = marine_data["model"]
    catch_model = catch_data["model"]
    catch_dist = catch_data["score_distribution"]
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = today + timedelta(days=num_days - 1)
    
    # データ取得
    forecast_data = fetch_openmeteo_all(today, end_date)
    
    # 昨日の海況初期値 (本来はDBから取るべきだが、一旦平均的な値 or 前回の予測値)
    last_marine = {
        'real_water_temp': 15.0, 'real_salinity': 30.0, 'real_do': 8.0, 
        'real_cod': 3.0, 'real_transparency': 3.0, 'real_wave_height': 0.5, 'real_river_discharge': 100.0
    }
    
    output_days = []
    
    for i in range(num_days):
        d = today + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        f = forecast_data.get(d_str, {})
        
        # 1. 海況予測 (Marine Env)
        marine_features = [
            f.get('avg_temp', 15), f.get('max_temp', 20), f.get('min_temp', 10),
            f.get('avg_wind_speed', 3), f.get('max_wind_speed', 5),
            f.get('precipitation', 0), 0, 0, # lag rain
            3, # lag wind
            f.get('daylight_hours', 8),
            get_tide_level(d),
            1 if d >= datetime(2017,8,1) and d <= datetime(2025,4,1) else 0, # Kuroshio
            last_marine['real_water_temp'], last_marine['real_salinity'], last_marine['real_do'],
            last_marine['real_cod'], last_marine['real_transparency'],
            last_marine['real_wave_height'], last_marine['real_river_discharge']
        ]
        
        # 2D配列に変換して推論
        marine_preds = marine_model.predict(np.array([marine_features]))[0]
        p_marine = {name: marine_preds[idx] for idx, name in enumerate(marine_data['targets'])}
        
        # 2. 釣果予測 (Catch Forecast)
        catch_features = [
            f.get('avg_temp', 15), f.get('max_temp', 20), f.get('min_temp', 10),
            f.get('avg_wind_speed', 3), f.get('max_wind_speed', 5),
            f.get('precipitation', 0), 0, # lag rain
            f.get('daylight_hours', 8),
            get_tide_level(d),
            1 if d >= datetime(2017,8,1) and d <= datetime(2025,4,1) else 0,
            p_marine['real_water_temp'], p_marine['real_salinity'], p_marine['real_do'],
            p_marine['real_transparency'], p_marine['real_wave_height'], p_marine['real_river_discharge']
        ]
        
        raw_catch = catch_model.predict(np.array([catch_features]))[0]
        # スコア化 (パーセンタイル)
        score = int(stats.percentileofscore(catch_dist, raw_catch, kind='weak'))
        score = max(10, min(100, score))
        
        # 昨日の状態を更新 (次のループ用)
        for k in last_marine:
            if k in p_marine: last_marine[k] = p_marine[k]
        
        # 理由(AIコメント)の生成
        reasons = []
        if p_marine['real_water_temp'] > 18: reasons.append("水温が適温で活性大")
        if p_marine['real_transparency'] < 2.0: reasons.append("適度な濁りで警戒心低下")
        if f.get('precipitation', 0) > 10: reasons.append("雨による水質変化に注意")
        if p_marine['real_wave_height'] > 1.5: reasons.append("波が高く底荒れの可能性")
        
        ai_comment = "、".join(reasons) if reasons else "安定した海況が予想されます。"

        output_days.append({
            "date": d.strftime("%Y/%m/%d"),
            "type": "forecast",
            "score": score,
            "weather": 'sunny' if f.get('precipitation', 0) < 1 else 'rain',
            "tide": ["若潮","長潮","小潮","中潮","大潮"][get_tide_level(d)],
            "marine": {
                "temp": round(p_marine['real_water_temp'], 1),
                "transparency": round(p_marine['real_transparency'], 1),
                "wave": round(p_marine['real_wave_height'], 1),
                "salinity": round(p_marine['real_salinity'], 1)
            },
            "ai_comment": ai_comment
        })

    # 保存
    out_path = "src/data/frontend_calendar.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output_days, f, ensure_ascii=False, indent=2)
    
    print(f"✅ カレンダー更新完了: {out_path}")

if __name__ == "__main__":
    generate_ai_calendar()

