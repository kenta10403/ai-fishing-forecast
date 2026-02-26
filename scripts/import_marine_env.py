import sqlite3
import pandas as pd
import numpy as np
import datetime
import os

DB_PATH = 'data/fishing_forecast.db'

def create_tables():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS marine_environment_history (
        date TEXT,
        area TEXT,
        wave_height REAL,
        wave_period REAL,
        salinity REAL,
        turbidity REAL,
        do_level REAL,
        is_kuroshio_meander BOOLEAN,
        PRIMARY KEY (date, area)
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS river_flow_history (
        date TEXT,
        area TEXT,
        river_name TEXT,
        total_flow REAL,
        PRIMARY KEY (date, area, river_name)
    )
    ''')
    conn.commit()
    return conn

def check_kuroshio_meander(date_str):
    """
    2017年8月〜2025年4月の黒潮大蛇行期間を判定
    """
    dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    start = datetime.datetime(2017, 8, 1)
    end = datetime.datetime(2025, 4, 30)
    return start <= dt <= end

def generate_marine_data(conn):
    """
    JMAやTBEICのAPIアクセス制限（IP BAN）が解除されるまでの間、
    システムアーキテクチャ(2段階AI)を最短で検証するために、
    既存の気象データ（風速・降水量）と相関を持たせた精緻な予測海況データを生成してDBに格納します。
    ※本番環境では、この関数を実際のスクレイピング関数に置き換えます。
    """
    print("Loading weather history to generate correlated marine data...")
    df_weather = pd.read_sql_query("SELECT * FROM weather_history", conn)
    
    if df_weather.empty:
        print("No weather data found. Please run import_jma_weather.py first.")
        return
        
    records = []
    
    for _, row in df_weather.iterrows():
        date = row['date']
        area = row['area']
        wind_speed = float(row['avg_wind_speed']) if pd.notna(row['avg_wind_speed']) else 3.0
        precip = float(row['precipitation']) if pd.notna(row['precipitation']) else 0.0
        temp = float(row['avg_temp']) if pd.notna(row['avg_temp']) else 15.0
        
        # 1. 波高・うねり予測モデル（風速と相関）
        # 基本波高0.5m + 風速による波立ち + ランダムノイズ
        base_wave = 0.5 + (wind_speed * 0.15) + np.random.normal(0, 0.2)
        wave_height = max(0.1, round(base_wave, 2))
        wave_period = max(3.0, round(5.0 + (wave_height * 1.5) + np.random.normal(0, 0.5), 1))
        
        # 2. 塩分濃度予測モデル（降水量と反比例）
        # 基本塩分33psu、大雨の翌日は激減する
        salinity_drop = (precip * 0.05)
        salinity = max(20.0, min(35.0, round(33.5 - salinity_drop + np.random.normal(0, 0.3), 1)))
        
        # 3. 濁度予測モデル（降水量と強い正の相関）
        turbidity_spike = (precip * 0.8)
        turbidity = max(1.0, round(2.5 + turbidity_spike + np.random.normal(0, 1.0), 1))
        
        # 4. 溶存酸素量 (DO) 予測モデル（水温と反比例）
        # 夏場は下がり、冬場は上がる
        do_level = max(3.0, min(14.0, round(12.0 - (temp * 0.2) + np.random.normal(0, 0.5), 1)))
        
        # 黒潮大蛇行フラグ
        is_meander = check_kuroshio_meander(date)
        
        records.append((
            date, area,
            wave_height, wave_period, salinity,
            turbidity, do_level, is_meander
        ))

    print(f"Inserting {len(records)} marine environment baseline records...")
    cursor = conn.cursor()
    cursor.executemany('''
        INSERT OR REPLACE INTO marine_environment_history (
            date, area, wave_height, wave_period, salinity, turbidity, do_level, is_kuroshio_meander
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', records)
    conn.commit()
    print("Pre-computation and DB insertion complete!")

if __name__ == '__main__':
    conn = create_tables()
    generate_marine_data(conn)
    conn.close()
