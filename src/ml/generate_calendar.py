import json
import logging
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

def fetch_last_weather_from_db(today):
    """
    【掟2: 現実同期】DBから前日・前々日の実測気象データを取得する。
    ハードコーディングされた固定値ではなく、実際の観測データで初期化する。
    DB取得失敗時はWarningログ付きでフォールバック値を使用する。
    """
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    day_before = (today - timedelta(days=2)).strftime("%Y-%m-%d")

    # フォールバック用デフォルト値
    last_weather = {
        'precipitation_lag1': 0,
        'precipitation_lag2': 0,
        'avg_wind_speed_lag1': 3.0
    }

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 前日データ取得 (lag1)
        cursor.execute(
            "SELECT precipitation, avg_wind_speed FROM weather_history WHERE date = ? AND area = '神奈川県'",
            (yesterday,)
        )
        row = cursor.fetchone()
        if row:
            last_weather['precipitation_lag1'] = row[0] if row[0] is not None else 0
            last_weather['avg_wind_speed_lag1'] = row[1] if row[1] is not None else 3.0
            print(f"  📊 掟2: 前日({yesterday})の実測値をDBから取得 → 降水量={last_weather['precipitation_lag1']}, 風速={last_weather['avg_wind_speed_lag1']}")
        else:
            logging.warning(f"掟2フォールバック: {yesterday}の気象データがDBに無いためデフォルト値を使用")

        # 前々日データ取得 (lag2)
        cursor.execute(
            "SELECT precipitation FROM weather_history WHERE date = ? AND area = '神奈川県'",
            (day_before,)
        )
        row = cursor.fetchone()
        if row:
            last_weather['precipitation_lag2'] = row[0] if row[0] is not None else 0
            print(f"  📊 掟2: 前々日({day_before})の実測値をDBから取得 → 降水量={last_weather['precipitation_lag2']}")
        else:
            logging.warning(f"掟2フォールバック: {day_before}の気象データがDBに無いためデフォルト値を使用")

        conn.close()
    except Exception as e:
        logging.warning(f"掟2フォールバック: DB接続エラー ({e})、デフォルト値を使用")

    return last_weather

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

    # 2. Marine Forecast (Wave + Sea Surface Temperature)
    url = f"https://marine-api.open-meteo.com/v1/marine?latitude={MARINE_LAT}&longitude={MARINE_LON}&daily=wave_height_max&hourly=sea_surface_temperature&timezone=Asia%2FTokyo&start_date={start_str}&end_date={end_str}"
    try:
        with urllib.request.urlopen(url) as res:
            d_json = json.loads(res.read().decode())
            daily = d_json.get('daily', {})
            hourly = d_json.get('hourly', {})
            
            # 波高 (daily)
            if 'time' in daily:
                for i, t in enumerate(daily['time']):
                    if t in data_map:
                        data_map[t]['wave_height'] = daily['wave_height_max'][i]
            
            # 海面水温 (hourly → daily平均に集約)
            if 'time' in hourly and 'sea_surface_temperature' in hourly:
                daily_sst = {}
                for ht, sst in zip(hourly['time'], hourly['sea_surface_temperature']):
                    d_key = ht[:10]
                    if d_key not in daily_sst:
                        daily_sst[d_key] = []
                    if sst is not None:
                        daily_sst[d_key].append(sst)
                for d_key, sst_list in daily_sst.items():
                    if d_key in data_map and sst_list:
                        data_map[d_key]['sea_surface_temperature'] = sum(sst_list) / len(sst_list)
                        
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
    
    # marine_data 自体が {target: {model, features, train_means}} の辞書形式
    catch_model = catch_data["model"]
    catch_dist = catch_data["score_distribution"]
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = today + timedelta(days=num_days - 1)
    
    # データ取得
    forecast_data = fetch_openmeteo_all(today, end_date)
    
    # (Issue #40: Train-Serving Skew対策により、海況モデルの自己回帰ラグを廃止したため初期値取得を削除)
    
    
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
        
    # 【掟2: 現実同期】DBから実測値を取得（ハードコーディング禁止）
    last_weather = fetch_last_weather_from_db(today)

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
        # 個別モデル形式に対応
        p_marine = {}
        base_marine_features = [
            f.get('avg_temp', 15), f.get('max_temp', 20), f.get('min_temp', 10),
            f.get('avg_wind_speed', 3), f.get('max_wind_speed', 5),
            f.get('precipitation', 0), last_weather['precipitation_lag1'], last_weather['precipitation_lag2'],
            last_weather['avg_wind_speed_lag1'],
            f.get('daylight_hours', 8),
            get_tide_level(d_str, tide_map),
            1 if d >= datetime(2017,8,1) and d <= datetime(2025,4,30) else 0, # Kuroshio
            month_sin, month_cos
        ]
        
        # ターゲットごとに予測
        for target, m_info in marine_data.items():
            
            # 特徴量 DataFrame の作成 (警告回避と整合性のために名前付きで渡す)
            feat_df = pd.DataFrame([base_marine_features], columns=m_info['features'])
            
            # 予測実行
            p_val = m_info['model'].predict(feat_df)[0]
            p_marine[target] = p_val

        # --- API直接値による上書き（モデル予測より実測/予報APIを優先） ---
        # 波高: APIから取得した値をそのまま使用（モデル予測をスキップ）
        if f.get('wave_height') is not None:
            p_marine['real_wave_height'] = f['wave_height']
        # 河川流量: APIから取得した値をそのまま使用（モデル予測をスキップ）
        if f.get('river_discharge') is not None:
            p_marine['real_river_discharge'] = f['river_discharge']
        # 海面水温: API値があればモデル予測より優先
        if f.get('sea_surface_temperature') is not None:
            p_marine['real_water_temp'] = f['sea_surface_temperature']
            print(f"  🌊 {d_str}: SST={f['sea_surface_temperature']:.1f}°C (API直接値)")

        # 2. 釣果予測 (Catch Forecast)
        catch_features = [
            f.get('avg_temp', 15), f.get('max_temp', 20), f.get('min_temp', 10),
            f.get('avg_wind_speed', 3), f.get('max_wind_speed', 5),
            f.get('precipitation', 0), last_weather['precipitation_lag1'],
            f.get('daylight_hours', 8),
            get_tide_level(d_str, tide_map),
            1 if d >= datetime(2017,8,1) and d <= datetime(2025,4,30) else 0,
            p_marine.get('real_water_temp', 18), 
            p_marine.get('real_salinity', 30), 
            p_marine.get('real_do', 8),
            p_marine.get('real_transparency', 1.0), 
            p_marine.get('real_wave_height', 0.5), 
            p_marine.get('real_river_discharge', 0.5),
            month_sin, month_cos, day_of_week, is_weekend
        ]
        
        # 釣果モデルも DataFrame 形式で推論
        catch_feat_df = pd.DataFrame([catch_features], columns=catch_data['features'])
        raw_catch = catch_model.predict(catch_feat_df)[0]
        
        # --- 手動補正一切なしの純粋なAIスコア ---
        # スコア化 (パーセンタイル)
        base_score = float(stats.percentileofscore(catch_dist, raw_catch, kind='weak'))
        score = int(base_score)
        score = max(5, min(100, score))
        
        # 【掟3: 移動平均ブレンド】予測値のブレを吸収 (7:3 = 当日予報:前日ラグ)
        # 予測値を100%信用せず、前日ラグとブレンドすることで雪だるま式エラーを防止
        last_weather['precipitation_lag2'] = last_weather['precipitation_lag1']
        last_weather['precipitation_lag1'] = (
            0.7 * f.get('precipitation', 0) + 0.3 * last_weather['precipitation_lag1']
        )
        last_weather['avg_wind_speed_lag1'] = (
            0.7 * f.get('avg_wind_speed', 3) + 0.3 * last_weather['avg_wind_speed_lag1']
        )
        
        # 3. AIコメント生成 (安全なアクセス)
        reasons = []
        month = d.month
        # 季節ごとの適水温の目安 (仮)
        if month in [3, 4, 5]: 
            min_temp, max_temp = 12, 18
        elif month in [6, 7, 8]: 
            min_temp, max_temp = 18, 25
        elif month in [9, 10, 11]: 
            min_temp, max_temp = 15, 20
        else: 
            min_temp, max_temp = 8, 15
            
        wt = p_marine.get('real_water_temp', 18)
        if wt > max_temp: reasons.append("水温が高めで夏バテ気味の魚も")
        elif min_temp <= wt <= max_temp: reasons.append("季節ごとの適水温で活性期待")
        elif wt < min_temp: reasons.append("水温が低く活性低下の懸念")

        if p_marine.get('real_transparency', 1.0) < 2.0: reasons.append("適度な濁りで警戒心低下")
        if f.get('precipitation', 0) > 10: reasons.append("雨による水質変化に注意")
        if p_marine.get('real_wave_height', 0.5) > 1.5: reasons.append("波が高く底荒れの可能性")
        
        ai_comment = "、".join(reasons) if reasons else "安定した海況が予想されます。"

        output_days.append({
            "date": d.strftime("%Y/%m/%d"),
            "type": "forecast",
            "score": score,
            "weather": 'sunny' if f.get('precipitation', 0) < 1 else 'rain',
            "tide": ["若潮","長潮","小潮","中潮","大潮"][get_tide_level(d_str, tide_map)],
            "marine": {
                "temp": round(p_marine.get('real_water_temp', 18), 1),
                "transparency": round(p_marine.get('real_transparency', 1.0), 1),
                "wave": round(p_marine.get('real_wave_height', 0.5), 1),
                "salinity": round(p_marine.get('real_salinity', 30), 1)
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
