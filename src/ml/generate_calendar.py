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
from astral import LocationInfo
from astral.sun import sun
from dotenv import load_dotenv

# -- Model Paths --
ML_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(ML_DIR)), "data", "fishing_forecast.db")
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(ML_DIR)), ".env")
load_dotenv(ENV_PATH)
MARINE_MODEL_PATH = os.path.join(ML_DIR, "model_marine_env_real.pkl")
CATCH_MODEL_PATH = os.path.join(ML_DIR, "model_catch_forecast_real.pkl")

from config import TOKYO_BAY_CENTER, ARAKAWA_ESTUARY, MET_NORWAY_USER_AGENT

# -- Coordinates --
MARINE_LAT = TOKYO_BAY_CENTER['lat']
MARINE_LON = TOKYO_BAY_CENTER['lon']

RIVER_LAT = ARAKAWA_ESTUARY['lat']
RIVER_LON = ARAKAWA_ESTUARY['lon']

# -- Astral Location for Daylight Calculation --
_LOCATION = LocationInfo("Tokyo Bay", "Japan", "Asia/Tokyo", MARINE_LAT, MARINE_LON)


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


def _calculate_daylight_hours(target_date):
    """astral ライブラリで日の出・日の入りから日照可能時間を算出"""
    try:
        s = sun(_LOCATION.observer, date=target_date, tzinfo=_LOCATION.timezone)
        daylight = (s['sunset'] - s['sunrise']).total_seconds() / 3600.0
        return daylight
    except Exception:
        return 8.0  # フォールバック


def _fetch_met_norway_weather(start_date, end_date, data_map):
    """
    【Phase 1: MET Norway Locationforecast 2.0】
    気象予報（気温・風速・降水量）を取得し、hourly → daily に集約する。
    """
    url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={MARINE_LAT}&lon={MARINE_LON}"
    req = urllib.request.Request(url, headers={
        'User-Agent': MET_NORWAY_USER_AGENT,
        'Accept': 'application/json'
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            d_json = json.loads(res.read().decode())

        timeseries = d_json.get('properties', {}).get('timeseries', [])
        if not timeseries:
            print("⚠️ MET Norway: timeseries が空です")
            return

        # Hourly data を日ごとに集約するためのバケット
        daily_buckets = {}

        for entry in timeseries:
            ts = entry.get('time', '')[:10]  # "2026-02-28T00:00:00Z" → "2026-02-28"
            if ts not in data_map:
                continue

            if ts not in daily_buckets:
                daily_buckets[ts] = {
                    'temps': [], 'winds': [], 'precip_sum': 0.0
                }

            instant = entry.get('data', {}).get('instant', {}).get('details', {})
            temps = instant.get('air_temperature')
            winds = instant.get('wind_speed')

            if temps is not None:
                daily_buckets[ts]['temps'].append(temps)
            if winds is not None:
                daily_buckets[ts]['winds'].append(winds)

            # 降水量: next_1_hours > next_6_hours の順に取得
            for period_key in ['next_1_hours', 'next_6_hours']:
                period_data = entry.get('data', {}).get(period_key, {})
                precip = period_data.get('details', {}).get('precipitation_amount')
                if precip is not None:
                    daily_buckets[ts]['precip_sum'] += precip
                    break  # 一番短い期間のデータを採用

        # daily集約 → data_map に書き込み
        for d_str, bucket in daily_buckets.items():
            if d_str not in data_map:
                continue

            if bucket['temps']:
                data_map[d_str]['max_temp'] = max(bucket['temps'])
                data_map[d_str]['min_temp'] = min(bucket['temps'])
                data_map[d_str]['avg_temp'] = sum(bucket['temps']) / len(bucket['temps'])

            if bucket['winds']:
                data_map[d_str]['max_wind_speed'] = max(bucket['winds'])
                data_map[d_str]['avg_wind_speed'] = sum(bucket['winds']) / len(bucket['winds'])
            else:
                data_map[d_str]['max_wind_speed'] = 0
                data_map[d_str]['avg_wind_speed'] = 0

            data_map[d_str]['precipitation'] = bucket['precip_sum']

            # 日照時間は astral で算出
            try:
                d_obj = datetime.strptime(d_str, "%Y-%m-%d")
                data_map[d_str]['daylight_hours'] = _calculate_daylight_hours(d_obj)
            except Exception:
                data_map[d_str]['daylight_hours'] = 8.0

        print(f"  ☀️ MET Norway: {len(daily_buckets)}日分の気象予報を取得")

    except Exception as e:
        print(f"MET Norway Weather API Error: {e}")


def _fetch_copernicus_marine(start_date, end_date, data_map):
    """
    【Phase 2: Copernicus Marine Service】
    海況予報（波高・海面水温）を取得する。
    copernicusmarine ライブラリを使用。
    """
    try:
        import copernicusmarine
    except ImportError:
        print("⚠️ copernicusmarine ライブラリが未インストールです。pip install copernicusmarine を実行してください。")
        return

    from config import COPERNICUS_USERNAME_ENV, COPERNICUS_PASSWORD_ENV
    if not os.environ.get(COPERNICUS_USERNAME_ENV) or not os.environ.get(COPERNICUS_PASSWORD_ENV):
        print(f"⚠️ Copernicus Marine の認証情報 ({COPERNICUS_USERNAME_ENV} / {COPERNICUS_PASSWORD_ENV}) が .env に設定されていません。スキップします。")
        return

    # -- 波高 (Significant Wave Height) --
    try:
        ds_wave = copernicusmarine.open_dataset(
            dataset_id="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
            variables=["VHM0"],
            minimum_latitude=MARINE_LAT - 0.5,
            maximum_latitude=MARINE_LAT + 0.5,
            minimum_longitude=MARINE_LON - 0.5,
            maximum_longitude=MARINE_LON + 0.5,
            start_datetime=start_date.strftime("%Y-%m-%dT00:00:00"),
            end_datetime=end_date.strftime("%Y-%m-%dT23:59:59"),
            username=os.environ.get(COPERNICUS_USERNAME_ENV),
            password=os.environ.get(COPERNICUS_PASSWORD_ENV),
        )
        # 空間平均 → 日次max
        wave_daily = ds_wave['VHM0'].mean(dim=['latitude', 'longitude']).resample(time='1D').max()
        for t in wave_daily.time.values:
            d_str = pd.Timestamp(t).strftime("%Y-%m-%d")
            if d_str in data_map:
                val = float(wave_daily.sel(time=t).values)
                if not np.isnan(val):
                    data_map[d_str]['wave_height'] = val
        ds_wave.close()
        print(f"  🌊 Copernicus Wave: {len(wave_daily.time)}日分の波高予報を取得")
    except Exception as e:
        print(f"Copernicus Wave API Error: {e}")

    # -- 海面水温 (Sea Surface Temperature) --
    try:
        ds_sst = copernicusmarine.open_dataset(
            dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
            variables=["thetao"],
            minimum_latitude=MARINE_LAT - 0.5,
            maximum_latitude=MARINE_LAT + 0.5,
            minimum_longitude=MARINE_LON - 0.5,
            maximum_longitude=MARINE_LON + 0.5,
            minimum_depth=0.0,
            maximum_depth=1.0,
            start_datetime=start_date.strftime("%Y-%m-%dT00:00:00"),
            end_datetime=end_date.strftime("%Y-%m-%dT23:59:59"),
            username=os.environ.get(COPERNICUS_USERNAME_ENV),
            password=os.environ.get(COPERNICUS_PASSWORD_ENV),
        )
        # 空間平均 → 日次平均
        sst_daily = ds_sst['thetao'].mean(dim=['latitude', 'longitude', 'depth']).resample(time='1D').mean()
        for t in sst_daily.time.values:
            d_str = pd.Timestamp(t).strftime("%Y-%m-%d")
            if d_str in data_map:
                val = float(sst_daily.sel(time=t).values)
                if not np.isnan(val):
                    data_map[d_str]['sea_surface_temperature'] = val
        ds_sst.close()
        print(f"  🌡️ Copernicus SST: {len(sst_daily.time)}日分の海面水温予報を取得")
    except Exception as e:
        print(f"Copernicus SST API Error: {e}")


def _fetch_river_discharge_from_db(data_map):
    """
    【Phase 3: 河川流量】
    DBから最新の実測河川流量を取得し、翌日以降は降水予報に連動した移動平均減衰ロジックで推定。
    """
    latest_discharge = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # marine_forecast_history から最新の river_discharge を取得 (旧 openmeteo_marine_history)
        cursor.execute("""
            SELECT river_discharge FROM marine_forecast_history 
            WHERE river_discharge IS NOT NULL 
            ORDER BY date DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            latest_discharge = row[0]
            print(f"  🏞️ 河川流量: DBから最新実測値={latest_discharge:.1f}m³/s を取得")
        conn.close()
    except Exception as e:
        logging.warning(f"河川流量DB取得エラー: {e}")

    if latest_discharge is None:
        latest_discharge = 50.0  # 荒川の平水流量の概算フォールバック値
        logging.warning("河川流量: DB取得失敗のためデフォルト値(50.0)を使用")

    # 推論ループ: 降水予報連動の移動平均減衰ロジック (掟3の応用)
    prev_discharge = latest_discharge
    for d_str in sorted(data_map.keys()):
        precip = data_map[d_str].get('precipitation', 0)
        # 降水量に応じて流量を増減: 降水が多い日は増加、少ない日は減衰
        # factor = 0.7 (ベース減衰) + 0.3 * (降水量/50に正規化, 上限1.0)
        factor = 0.7 + 0.3 * min(precip / 50.0, 1.0)
        river_discharge = prev_discharge * factor
        # 下限設定 (完全に0にはならない)
        river_discharge = max(river_discharge, 10.0)
        data_map[d_str]['river_discharge'] = river_discharge
        prev_discharge = river_discharge


def fetch_forecast_all(start_date, end_date):
    """
    MET Norway・Copernicus・国交省DBから、推論に必要な気象・海況予報を一括取得。
    旧 fetch_openmeteo_all() を完全置換。
    """
    data_map = {}
    dates = pd.date_range(start_date, end_date)
    for d in dates:
        data_map[d.strftime("%Y-%m-%d")] = {}

    # 1. 気象予報 (MET Norway Locationforecast 2.0)
    _fetch_met_norway_weather(start_date, end_date, data_map)

    # 2. 海況予報 (Copernicus Marine: 波高 + SST)
    _fetch_copernicus_marine(start_date, end_date, data_map)

    # 3. 河川流量 (DB実測値 + 移動平均減衰)
    _fetch_river_discharge_from_db(data_map)

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
    
    # データ取得 (MET Norway + Copernicus + 国交省DB)
    forecast_data = fetch_forecast_all(today, end_date)
    
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
        # 波高: Copernicus から取得した値をそのまま使用（モデル予測をスキップ）
        if f.get('wave_height') is not None:
            p_marine['real_wave_height'] = f['wave_height']
        # 河川流量: DB実測値+減衰ロジックの値をそのまま使用
        if f.get('river_discharge') is not None:
            p_marine['real_river_discharge'] = f['river_discharge']
        # 海面水温: Copernicus 値があればモデル予測より優先
        if f.get('sea_surface_temperature') is not None:
            p_marine['real_water_temp'] = f['sea_surface_temperature']
            print(f"  🌊 {d_str}: SST={f['sea_surface_temperature']:.1f}°C (Copernicus直接値)")

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
