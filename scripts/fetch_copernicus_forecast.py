"""
Copernicus Marine Service から今後10日間の波浪・海面水温予報を取得し、
marine_forecast_history テーブルに保存するスクリプト。
これにより、リアルタイムの推論スクリプト (generate_calendar.py) による同期呼び出しを避け、
パフォーマンスと安定性を向上させます。

使用方法:
    python scripts/fetch_copernicus_forecast.py
"""
import os
import sys
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "ml"))
from config import TOKYO_BAY_CENTER, COPERNICUS_USERNAME_ENV, COPERNICUS_PASSWORD_ENV

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(ENV_PATH)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'fishing_forecast.db')
LAT = TOKYO_BAY_CENTER['lat']
LON = TOKYO_BAY_CENTER['lon']


def init_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS marine_forecast_history (
            date TEXT PRIMARY KEY,
            wave_height_max REAL,
            wave_direction_dominant INTEGER,
            river_discharge REAL
        )
    ''')
    # sea_surface_temperatureカラムが無ければ追加
    try:
        cursor.execute("ALTER TABLE marine_forecast_history ADD COLUMN sea_surface_temperature REAL")
    except sqlite3.OperationalError:
        pass # Column exists
    conn.commit()
    conn.close()

def fetch_and_save_forecast():
    if not os.environ.get(COPERNICUS_USERNAME_ENV) or not os.environ.get(COPERNICUS_PASSWORD_ENV):
        print(f"❌ エラー: Copernicus Marine の認証情報 ({COPERNICUS_USERNAME_ENV} / {COPERNICUS_PASSWORD_ENV}) が .env に設定されていません。")
        return

    import copernicusmarine

    init_table()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = today + timedelta(days=9)
    print(f"📆 Fetching Copernicus forecast: {today.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")

    # -- 波高データ --
    try:
        ds_wave = copernicusmarine.open_dataset(
            dataset_id="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
            variables=["VHM0"],
            minimum_latitude=LAT - 0.5,
            maximum_latitude=LAT + 0.5,
            minimum_longitude=LON - 0.5,
            maximum_longitude=LON + 0.5,
            start_datetime=today.strftime("%Y-%m-%dT00:00:00"),
            end_datetime=end_date.strftime("%Y-%m-%dT23:59:59"),
            username=os.environ.get(COPERNICUS_USERNAME_ENV),
            password=os.environ.get(COPERNICUS_PASSWORD_ENV),
        )
        wave_daily = ds_wave['VHM0'].mean(dim=['latitude', 'longitude']).resample(time='1D').max()

        for t in wave_daily.time.values:
            d_str = pd.Timestamp(t).strftime("%Y-%m-%d")
            val = float(wave_daily.sel(time=t).values)
            if not np.isnan(val):
                cursor.execute("""
                    INSERT INTO marine_forecast_history (date, wave_height_max)
                    VALUES (?, ?)
                    ON CONFLICT(date) DO UPDATE SET wave_height_max = excluded.wave_height_max
                """, (d_str, val))
        ds_wave.close()
        print(f"  ✅ Wave: {len(wave_daily.time)} records saved")
    except Exception as e:
        print(f"  ⚠️ Wave Error: {e}")

    # -- SSTデータ --
    try:
        ds_sst = copernicusmarine.open_dataset(
            dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
            variables=["thetao"],
            minimum_latitude=LAT - 0.5,
            maximum_latitude=LAT + 0.5,
            minimum_longitude=LON - 0.5,
            maximum_longitude=LON + 0.5,
            minimum_depth=0.0,
            maximum_depth=1.0,
            start_datetime=today.strftime("%Y-%m-%dT00:00:00"),
            end_datetime=end_date.strftime("%Y-%m-%dT23:59:59"),
            username=os.environ.get(COPERNICUS_USERNAME_ENV),
            password=os.environ.get(COPERNICUS_PASSWORD_ENV),
        )
        sst_daily = ds_sst['thetao'].mean(dim=['latitude', 'longitude', 'depth']).resample(time='1D').mean()

        for t in sst_daily.time.values:
            d_str = pd.Timestamp(t).strftime("%Y-%m-%d")
            val = float(sst_daily.sel(time=t).values)
            if not np.isnan(val):
                cursor.execute("""
                    INSERT INTO marine_forecast_history (date, sea_surface_temperature)
                    VALUES (?, ?)
                    ON CONFLICT(date) DO UPDATE SET sea_surface_temperature = excluded.sea_surface_temperature
                """, (d_str, val))
        ds_sst.close()
        print(f"  ✅ SST: {len(sst_daily.time)} records saved")
    except Exception as e:
        print(f"  ⚠️ SST Error: {e}")

    conn.commit()
    conn.close()
    print("🎉 完了！")

if __name__ == "__main__":
    fetch_and_save_forecast()
