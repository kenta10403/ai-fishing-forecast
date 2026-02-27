"""
Copernicus Marine Service から過去の波浪・海面水温データを取得し、
marine_forecast_history テーブルに保存するスクリプト。

使用方法:
    python scripts/fetch_copernicus_marine.py [start_year] [end_year]
    例: python scripts/fetch_copernicus_marine.py 2020 2024

前提条件:
    - pip install copernicusmarine
    - Copernicus Marine のアカウント登録済み
    - 環境変数 COPERNICUS_MARINE_USERNAME / COPERNICUS_MARINE_PASSWORD を設定
"""
import os
import sys
import sqlite3
from datetime import datetime

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
    conn.commit()
    conn.close()


def fetch_and_save(start_year, end_year):
    if not os.environ.get(COPERNICUS_USERNAME_ENV) or not os.environ.get(COPERNICUS_PASSWORD_ENV):
        print(f"❌ エラー: Copernicus Marine の認証情報 ({COPERNICUS_USERNAME_ENV} / {COPERNICUS_PASSWORD_ENV}) が .env に設定されていません。")
        print("アカウント登録後、.env に設定してから再実行してください。")
        return

    import copernicusmarine

    init_table()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    total_saved = 0

    for year in range(start_year, end_year + 1):
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        print(f"📆 Processing {year}...")

        # -- 波高データ --
        try:
            ds_wave = copernicusmarine.open_dataset(
                dataset_id="cmems_mod_glo_wav_anfc_0.083deg_PT3H-i",
                variables=["VHM0"],
                minimum_latitude=LAT - 0.5,
                maximum_latitude=LAT + 0.5,
                minimum_longitude=LON - 0.5,
                maximum_longitude=LON + 0.5,
                start_datetime=f"{start_date}T00:00:00",
                end_datetime=f"{end_date}T23:59:59",
                username=os.environ.get(COPERNICUS_USERNAME_ENV),
                password=os.environ.get(COPERNICUS_PASSWORD_ENV),
            )
            wave_daily = ds_wave['VHM0'].mean(dim=['latitude', 'longitude']).resample(time='1D').max()

            for t in wave_daily.time.values:
                d_str = pd.Timestamp(t).strftime("%Y-%m-%d")
                val = float(wave_daily.sel(time=t).values)
                if not np.isnan(val):
                    cursor.execute("""
                        INSERT OR REPLACE INTO marine_forecast_history (date, wave_height_max)
                        VALUES (?, ?)
                        ON CONFLICT(date) DO UPDATE SET wave_height_max = excluded.wave_height_max
                    """, (d_str, val))
                    total_saved += 1

            ds_wave.close()
            print(f"  ✅ Wave: {len(wave_daily.time)} records")
        except Exception as e:
            print(f"  ⚠️ Wave Error for {year}: {e}")

        conn.commit()

    conn.close()
    print(f"\n🎉 完了！合計 {total_saved} レコードを保存しました。")


if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 2020
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    fetch_and_save(start, end)
