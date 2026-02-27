import json
import os
import urllib.request
from datetime import datetime, timedelta

import sqlite3
import joblib
import numpy as np
import pandas as pd
import scipy.stats as stats

# -- Model Paths --
ML_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(ML_DIR)), "data", "fishing_forecast.db")
MARINE_MODEL_PATH = os.path.join(ML_DIR, "model_marine_env_real.pkl")
CATCH_MODEL_PATH = os.path.join(ML_DIR, "model_catch_forecast_real.pkl")

from config import TOKYO_BAY_CENTER, ARAKAWA_ESTUARY

# -- Coordinates --
MARINE_LAT = TOKYO_BAY_CENTER['lat']
MARINE_LON = TOKYO_BAY_CENTER['lon']

RIVER_LAT = ARAKAWA_ESTUARY['lat']
RIVER_LON = ARAKAWA_ESTUARY['lon']

def get_tide_level(d_str, tide_map):
    """
    DBから取得した潮回りを数値化 (0:若潮 ... 4:大潮)
    """
    tide = tide_map.get(d_str, "中潮") # デフォルトは中潮
    
    if "大潮" in tide: return 4
    if "中潮" in tide: return 3
    if "小潮" in tide: return 2
    if "長潮" in tide: return 1
    if "若潮" in tide: return 0
    return 3 # 不明な場合は中潮扱い

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
    url = f"https://api.open-meteo.com/v1/forecast?latitude={MARINE_LAT}&longitude={MARINE_LON}&hourly=windspeed_10m&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,sunshine_duration&wind_speed_unit=ms&timezone=Asia%2FTokyo&start_date={start_str}&end_date={end_str}"
    try:
        with urllib.request.urlopen(url) as res:
            d_json = json.loads(res.read().decode())
            daily = d_json.get('daily', {})
            hourly = d_json.get('hourly', {})

            daily_wind_avg = {}
            if 'time' in hourly and 'windspeed_10m' in hourly:
                for ht, hw in zip(hourly['time'], hourly['windspeed_10m']):
                    d_key = ht[:10]
                    if d_key not in daily_wind_avg:
                        daily_wind_avg[d_key] = []
                    if hw is not None:
                        daily_wind_avg[d_key].append(hw)

            if 'time' in daily:
                for i, t in enumerate(daily['time']):
                    if t in data_map:
                        data_map[t]['max_temp'] = daily['temperature_2m_max'][i]
                        data_map[t]['min_temp'] = daily['temperature_2m_min'][i]
                        data_map[t]['avg_temp'] = (daily['temperature_2m_max'][i] + daily['temperature_2m_min'][i]) / 2
                        data_map[t]['precipitation'] = daily['precipitation_sum'][i]
                        
                        max_w = daily['windspeed_10m_max'][i]
                        data_map[t]['max_wind_speed'] = max_w if max_w is not None else 0
                        
                        if t in daily_wind_avg and len(daily_wind_avg[t]) > 0:
                            data_map[t]['avg_wind_speed'] = sum(daily_wind_avg[t]) / len(daily_wind_avg[t])
                        else:
                            data_map[t]['avg_wind_speed'] = (max_w * 0.7) if max_w is not None else 0
                            
                        # Radiation to Daylight Hours approx
                        if 'sunshine_duration' in daily and daily['sunshine_duration'][i] is not None:
                            data_map[t]['daylight_hours'] = daily['sunshine_duration'][i] / 3600.0
                        else:
                            data_map[t]['daylight_hours'] = 8.0 # default fallback 
    except Exception as e: print(f"Weather API Error: {e}")

    # 2. Marine Forecast (Wave)
    url = f"https://marine-api.open-meteo.com/v1/marine?latitude={MARINE_LAT}&longitude={MARINE_LON}&daily=wave_height_max&timezone=Asia%2FTokyo&start_date={start_str}&end_date={end_str}"
    try:
        with urllib.request.urlopen(url) as res:
            d_json = json.loads(res.read().decode())
            daily = d_json['daily']
            for i, t in enumerate(daily['time']):
                if t in data_map:
                    data_map[t]['wave_height'] = daily['wave_height_max'][i]
    except Exception as e: print(f"Marine API Error: {e}")

    # 3. Flood Forecast (River Discharge)
    url = f"https://flood-api.open-meteo.com/v1/flood?latitude={RIVER_LAT}&longitude={RIVER_LON}&daily=river_discharge&timezone=Asia%2FTokyo&start_date={start_str}&end_date={end_str}"
    try:
        with urllib.request.urlopen(url) as res:
            d_json = json.loads(res.read().decode())
            daily = d_json['daily']
            for i, t in enumerate(daily['time']):
                if t in data_map:
                    data_map[t]['river_discharge'] = daily['river_discharge'][i]
    except Exception as e: print(f"Flood API Error: {e}")

    return data_map

def generate_ai_calendar(num_days=10):
    """
    2段階AIモデルを使って最新の釣果予測カレンダーを生成
    """
    print("🚀 2段階AI推論パイプライン実行中 (データ駆動型)...")
    
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
    
    # 昨日の海況初期値 (DBから最新の実測値を取得)
    last_marine = {
        'real_water_temp': 15.0, 'real_salinity': 30.0, 'real_do': 8.0, 
        'real_cod': 3.0, 'real_transparency': 3.0, 'real_wave_height': 0.5, 'real_river_discharge': 100.0
    }
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # marine_environment_history と tokyo_bay_marine_data
        # tokyo_bay_marine_data から取得を試みる
        cursor.execute("""
            SELECT water_temp, salinity, do_level, cod, transparency
            FROM tokyo_bay_marine_data
            ORDER BY date DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            last_marine['real_water_temp'] = float(row[0]) if row[0] is not None else 15.0
            last_marine['real_salinity'] = float(row[1]) if row[1] is not None else 30.0
            last_marine['real_do'] = float(row[2]) if row[2] is not None else 8.0
            last_marine['real_cod'] = float(row[3]) if row[3] is not None else 3.0
            last_marine['real_transparency'] = float(row[4]) if row[4] is not None else 3.0
            
        # 波高、河川流量は openmeteo_marine_history
        cursor.execute("""
            SELECT wave_height_max, river_discharge
            FROM openmeteo_marine_history
            ORDER BY date DESC LIMIT 1
        """)
        row2 = cursor.fetchone()
        if row2:
            last_marine['real_wave_height'] = float(row2[0]) if row2[0] is not None else 0.5
            last_marine['real_river_discharge'] = float(row2[1]) if row2[1] is not None else 100.0
            
        conn.close()
    except Exception as e:
        print(f"DBから初期値取得エラー: {e} (デフォルト値を使用します)")
    
    # 潮汐データの取得 (予測期間分)
    tide_map = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        end_str = end_date.strftime("%Y-%m-%d")
        start_str = today.strftime("%Y-%m-%d")
        cursor.execute("SELECT date, tide FROM tide_history WHERE date >= ? AND date <= ?", (start_str, end_str))
        for row in cursor.fetchall():
            tide_map[row[0]] = row[1] if row[1] else "中潮"
        conn.close()
    except Exception as e:
        print(f"DBから潮汐データ取得エラー: {e}")
        
    output_days = []
    
    for i in range(num_days):
        d = today + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        f = forecast_data.get(d_str, {})
        if not f:
            print(f"Skipping {d_str} (API data unavailable)")
            continue
        
        month = d.month
        month_sin = np.sin(2 * np.pi * month / 12)
        month_cos = np.cos(2 * np.pi * month / 12)
        day_of_week = d.weekday()
        is_weekend = 1 if day_of_week in [5, 6] else 0

        # 1. 海況予測 (Marine Env)
        marine_features = [
            f.get('avg_temp', 15), f.get('max_temp', 20), f.get('min_temp', 10),
            f.get('avg_wind_speed', 3), f.get('max_wind_speed', 5),
            f.get('precipitation', 0), 0, 0, # lag rain
            3, # lag wind
            f.get('daylight_hours', 8),
            get_tide_level(d_str, tide_map),
            1 if d >= datetime(2017,8,1) and d <= datetime(2025,4,30) else 0, # Kuroshio
            last_marine['real_water_temp'], last_marine['real_salinity'], last_marine['real_do'],
            last_marine['real_cod'], last_marine['real_transparency'],
            last_marine['real_wave_height'], last_marine['real_river_discharge'],
            month_sin, month_cos
        ]
        
        marine_preds = marine_model.predict(np.array([marine_features]))[0]
        p_marine = {name: marine_preds[idx] for idx, name in enumerate(marine_data['targets'])}
        
        # 2. 釣果予測 (Catch Forecast)
        catch_features = [
            f.get('avg_temp', 15), f.get('max_temp', 20), f.get('min_temp', 10),
            f.get('avg_wind_speed', 3), f.get('max_wind_speed', 5),
            f.get('precipitation', 0), 0, # lag rain
            f.get('daylight_hours', 8),
            get_tide_level(d_str, tide_map),
            1 if d >= datetime(2017,8,1) and d <= datetime(2025,4,30) else 0,
            p_marine['real_water_temp'], p_marine['real_salinity'], p_marine['real_do'],
            p_marine['real_transparency'], p_marine['real_wave_height'], p_marine['real_river_discharge'],
            month_sin, month_cos, day_of_week, is_weekend
        ]
        
        raw_catch = catch_model.predict(np.array([catch_features]))[0]
        
        # --- 手動補正一切なしの純粋なAIスコア ---
        # スコア化 (パーセンタイル)
        base_score = float(stats.percentileofscore(catch_dist, raw_catch, kind='weak'))
        score = int(base_score)
        score = max(5, min(100, score))
        
        # 昨日の状態を更新 (次のループ用)
        for k in last_marine:
            if k in p_marine: last_marine[k] = p_marine[k]
        
        # 理由(AIコメント)の生成
        reasons = []
        
        # 季節別の適水温 (東京湾基準の概算)
        if month in [3, 4, 5]: 
            min_temp, max_temp = 12, 18
        elif month in [6, 7, 8]: 
            min_temp, max_temp = 18, 25
        elif month in [9, 10, 11]: 
            min_temp, max_temp = 15, 20
        else: 
            min_temp, max_temp = 8, 15
            
        wt = p_marine['real_water_temp']
        if wt > max_temp: reasons.append("水温が高めで夏バテ気味の魚も")
        elif min_temp <= wt <= max_temp: reasons.append("季節ごとの適水温で活性期待")
        elif wt < min_temp: reasons.append("水温が低く活性低下の懸念")

        if p_marine['real_transparency'] < 2.0: reasons.append("適度な濁りで警戒心低下")
        if f.get('precipitation', 0) > 10: reasons.append("雨による水質変化に注意")
        if p_marine['real_wave_height'] > 1.5: reasons.append("波が高く底荒れの可能性")
        
        ai_comment = "、".join(reasons) if reasons else "安定した海況が予想されます。"

        output_days.append({
            "date": d.strftime("%Y/%m/%d"),
            "type": "forecast",
            "score": score,
            "weather": 'sunny' if f.get('precipitation', 0) < 1 else 'rain',
            "tide": ["若潮","長潮","小潮","中潮","大潮"][get_tide_level(d_str, tide_map)],
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
