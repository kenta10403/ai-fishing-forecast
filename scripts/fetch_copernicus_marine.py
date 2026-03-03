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

    # --- Phase 1: Wave Data (Quick Harvest - All years first) ---
    print(f"\n🌊 Phase 1: Wave Data History ({start_year} - {end_year})")
    for year in range(start_year, end_year + 1):
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        print(f"📆 Wave: Processing {year}...")
        try:
            wave_id = "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i" if year >= 2022 else "cmems_mod_glo_wav_my_0.2deg_PT3H-i"
            ds_wave = copernicusmarine.open_dataset(
                dataset_id=wave_id, variables=["VHM0"],
                minimum_latitude=LAT - 0.5, maximum_latitude=LAT + 0.5,
                minimum_longitude=LON - 0.5, maximum_longitude=LON + 0.5,
                start_datetime=f"{start_date}T00:00:00", end_datetime=f"{end_date}T23:59:59",
                username=os.environ.get(COPERNICUS_USERNAME_ENV), password=os.environ.get(COPERNICUS_PASSWORD_ENV),
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
                    total_saved += 1
            ds_wave.close()
            conn.commit()
            print(f"  ✅ Wave: {year} completed ({len(wave_daily.time)} days).")
        except Exception as e:
            print(f"  ⚠️ Wave Error for {year}: {e}")

    # --- Phase 2: Physics Data (Heavy - Recent first) ---
    print(f"\n🌡️ Phase 2: Physics Data History ({end_year} -> {start_year})")
    for year in range(end_year, start_year - 1, -1):
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        print(f"📆 Physics: Processing {year}...")
        try:
            print(f"  📥 Physics データ取得中 (read_dataframe)...")
            phy_id = "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m" if year >= 2025 else "cmems_mod_glo_phy_my_0.083deg_P1D-m"
            df_phy = copernicusmarine.read_dataframe(
                dataset_id=phy_id,
                variables=["so", "zos", "uo", "vo"],
                minimum_latitude=LAT - 0.1, maximum_latitude=LAT + 0.1,
                minimum_longitude=LON - 0.1, maximum_longitude=LON + 0.1,
                start_datetime=f"{start_date}T00:00:00", end_datetime=f"{end_date}T23:59:59",
                username=os.environ.get(COPERNICUS_USERNAME_ENV), password=os.environ.get(COPERNICUS_PASSWORD_ENV),
            )
            
            if df_phy.empty:
                print(f"  ⚠️ Physics: No data for {year}")
                continue

            # MultiIndex を解除してカラムとして扱えるようにする
            df_phy = df_phy.reset_index()

            # カラム名が time だったり date だったりする場合があるため柔軟に対応
            time_col = 'time' if 'time' in df_phy.columns else ('date' if 'date' in df_phy.columns else None)
            if not time_col:
                print(f"  ⚠️ Physics: Time column not found. Columns: {df_phy.columns.tolist()}")
                continue
            
            # depthカラムがある場合は最小値(表層)のみ使用
            if 'depth' in df_phy.columns:
                min_depth = df_phy['depth'].min()
                df_phy = df_phy[df_phy['depth'] == min_depth]
            
            df_phy['date_short'] = pd.to_datetime(df_phy[time_col]).dt.strftime('%Y-%m-%d')
            phy_daily = df_phy.groupby('date_short').mean()

            for d_str, row in phy_daily.iterrows():
                sal, ssh, u, v = row['so'], row['zos'], row['uo'], row['vo']
                if not np.isnan(sal):
                    cursor.execute("""
                        INSERT INTO marine_forecast_history (date, salinity, sea_surface_height, current_u, current_v)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(date) DO UPDATE SET 
                            salinity = excluded.salinity, 
                            sea_surface_height = excluded.sea_surface_height, 
                            current_u = excluded.current_u, 
                            current_v = excluded.current_v
                    """, (d_str, sal, ssh, u, v))
            conn.commit()
            print(f"  ✅ Physics: {year} completed.")
        except Exception as e:
            print(f"  ⚠️ Physics Error for {year}: {e}")

    # --- Phase 3: BGC Data (Heavy - Recent first) ---
    print(f"\n🧪 Phase 3: BGC Data History ({end_year} -> {start_year})")
    for year in range(end_year, start_year - 1, -1):
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        print(f"📆 BGC: Processing {year}...")
        try:
            print(f"  📥 BGC データ取得中 (read_dataframe)...")
            
            df_bgc_list = []
            if year >= 2025:
                # ANFC では変数が別データセットに分かれている
                print("    -> 2025年以降のため、BGCデータを-pftと-bioに分割して取得します...")
                try:
                    df_chl = copernicusmarine.read_dataframe(
                        dataset_id="cmems_mod_glo_bgc-pft_anfc_0.25deg_P1D-m", variables=["chl"],
                        minimum_latitude=LAT - 1.0, maximum_latitude=LAT + 0.5,
                        minimum_longitude=LON - 1.0, maximum_longitude=LON + 0.5,
                        start_datetime=f"{start_date}T00:00:00", end_datetime=f"{end_date}T23:59:59",
                        username=os.environ.get(COPERNICUS_USERNAME_ENV), password=os.environ.get(COPERNICUS_PASSWORD_ENV),
                    ).reset_index()
                    df_bgc_list.append(df_chl)
                except Exception as e:
                    print(f"    ⚠️ BGC chl Error: {e}")
                    
                try:
                    df_o2 = copernicusmarine.read_dataframe(
                        dataset_id="cmems_mod_glo_bgc-bio_anfc_0.25deg_P1D-m", variables=["o2"],
                        minimum_latitude=LAT - 1.0, maximum_latitude=LAT + 0.5,
                        minimum_longitude=LON - 1.0, maximum_longitude=LON + 0.5,
                        start_datetime=f"{start_date}T00:00:00", end_datetime=f"{end_date}T23:59:59",
                        username=os.environ.get(COPERNICUS_USERNAME_ENV), password=os.environ.get(COPERNICUS_PASSWORD_ENV),
                    ).reset_index()
                    df_bgc_list.append(df_o2)
                except Exception as e:
                    print(f"    ⚠️ BGC o2 Error: {e}")
            else:
                # MY データは1つにまとまっている
                df_bgc = copernicusmarine.read_dataframe(
                    dataset_id="cmems_mod_glo_bgc_my_0.25deg_P1D-m", variables=["chl", "o2"],
                    minimum_latitude=LAT - 1.0, maximum_latitude=LAT + 0.5,
                    minimum_longitude=LON - 1.0, maximum_longitude=LON + 0.5,
                    start_datetime=f"{start_date}T00:00:00", end_datetime=f"{end_date}T23:59:59",
                    username=os.environ.get(COPERNICUS_USERNAME_ENV), password=os.environ.get(COPERNICUS_PASSWORD_ENV),
                ).reset_index()
                df_bgc_list.append(df_bgc)
                
            # 全リストを統合して処理
            for df_bgc in df_bgc_list:
                if df_bgc.empty:
                    continue
                time_col = 'time' if 'time' in df_bgc.columns else ('date' if 'date' in df_bgc.columns else None)
                if not time_col:
                    continue
                
                if 'depth' in df_bgc.columns:
                    min_depth = df_bgc['depth'].min()
                    df_bgc = df_bgc[df_bgc['depth'] == min_depth]
                    
                df_bgc['date_short'] = pd.to_datetime(df_bgc[time_col]).dt.strftime('%Y-%m-%d')
                bgc_daily = df_bgc.groupby('date_short').mean()

                has_chl = 'chl' in bgc_daily.columns
                has_o2 = 'o2' in bgc_daily.columns

                for d_str, row in bgc_daily.iterrows():
                    chl = float(row['chl']) if has_chl else np.nan
                    o2 = float(row['o2']) if has_o2 else np.nan
                    
                    if not np.isnan(chl) or not np.isnan(o2):
                        # まず挿入して存在させる
                        cursor.execute("""
                            INSERT OR IGNORE INTO marine_forecast_history (date) VALUES (?)
                        """, (d_str,))
                        
                        if has_chl and not np.isnan(chl):
                            cursor.execute("""
                                UPDATE marine_forecast_history SET chlorophyll = ? WHERE date = ?
                            """, (chl, d_str))
                            
                        if has_o2 and not np.isnan(o2):
                            cursor.execute("""
                                UPDATE marine_forecast_history SET oxygen = ? WHERE date = ?
                            """, (o2, d_str))
                            
            conn.commit()
            print(f"  ✅ BGC: {year} completed.")
        except Exception as e:
            print(f"  ⚠️ BGC Error for {year}: {e}")

    conn.close()
    print(f"\n🎉 全フェーズ完了！")


if __name__ == "__main__":
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 2020
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    fetch_and_save(start, end)
