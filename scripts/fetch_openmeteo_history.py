import urllib.request
import urllib.parse
import json
import sqlite3
import time
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__abspath__)), 'data', 'fishing_forecast.db') if '__abspath__' in globals() else 'data/fishing_forecast.db'

# 東京湾の波 (Marine API) - 大和町や木更津沖など
MARINE_LAT = 35.5
MARINE_LON = 139.9

# 荒川河口付近の流量 (Flood API)
RIVER_LAT = 35.65
RIVER_LON = 139.85

def init_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS openmeteo_marine_history (
            date TEXT PRIMARY KEY,
            wave_height_max REAL,
            wave_direction_dominant INTEGER,
            river_discharge REAL
        )
    ''')
    conn.commit()
    conn.close()

def save_to_db(records):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for date_str, data in records.items():
        cursor.execute('''
            INSERT OR REPLACE INTO openmeteo_marine_history 
            (date, wave_height_max, wave_direction_dominant, river_discharge)
            VALUES (?, ?, ?, ?)
        ''', (
            date_str, 
            data.get('wave_height_max'), 
            data.get('wave_direction_dominant'), 
            data.get('river_discharge')
        ))
        
    conn.commit()
    conn.close()

def fetch_year(year):
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    records = {}
    
    # --- 1. 波浪データの取得 (Marine API) ---
    marine_url = f"https://marine-api.open-meteo.com/v1/marine?latitude={MARINE_LAT}&longitude={MARINE_LON}&daily=wave_height_max,wave_direction_dominant&timezone=Asia%2FTokyo&start_date={start_date}&end_date={end_date}"
    try:
        req = urllib.request.Request(marine_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            if 'daily' in data:
                dates = data['daily']['time']
                waves = data['daily']['wave_height_max']
                dirs = data['daily']['wave_direction_dominant']
                for i, d in enumerate(dates):
                    records[d] = {
                        'wave_height_max': waves[i] if waves[i] is not None else None,
                        'wave_direction_dominant': dirs[i] if dirs[i] is not None else None,
                    }
    except Exception as e:
        print(f"Error fetching marine data for {year}: {e}")
        
    time.sleep(1) # APIレートリミット対策

    # --- 2. 河川流量データの取得 (Flood API) ---
    # GloFASはUTCベースなのでtimezone指定なし
    river_url = f"https://flood-api.open-meteo.com/v1/flood?latitude={RIVER_LAT}&longitude={RIVER_LON}&daily=river_discharge&start_date={start_date}&end_date={end_date}"
    try:
        req = urllib.request.Request(river_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            if 'daily' in data:
                dates = data['daily']['time']
                flows = data['daily']['river_discharge']
                for i, d in enumerate(dates):
                    if d not in records:
                        records[d] = {}
                    records[d]['river_discharge'] = flows[i] if flows[i] is not None else None
    except Exception as e:
        print(f"Error fetching river data for {year}: {e}")
        
    time.sleep(1)
    
    return records

def main():
    print("🌊 Open-Meteo 歴史データ（波浪＆河川流量）取得開始")
    print("==================================================")
    
    # テーブル作成
    init_table()
    
    total_saved = 0
    for year in range(2009, 2025):
        print(f"📆 Processing {year}...")
        records = fetch_year(year)
        if records:
            save_to_db(records)
            total_saved += len(records)
            print(f"  ✅ Saved {len(records)} records.")
            
    print("==================================================")
    print(f"🎉 完了！合計 {total_saved} レコード（波浪・流量）をDBに保存しました。")

if __name__ == "__main__":
    main()
