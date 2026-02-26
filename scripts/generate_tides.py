import sqlite3
import ephem
from datetime import datetime, timedelta
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fishing_forecast.db")

def get_tide(moon_age):
    # 月齢の小数点以下を四捨五入して整数にする
    age = int(round(moon_age)) % 30
    
    if age in [0, 1, 2, 14, 15, 16, 17, 29]:
        return "大潮"
    elif age in [3, 4, 5, 6, 12, 13, 18, 19, 20, 21, 27, 28]:
        return "中潮"
    elif age in [7, 8, 9, 22, 23, 24]:
        return "小潮"
    elif age in [10, 25]:
        return "長潮"
    elif age in [11, 26]:
        return "若潮"
    return "不明"

def generate_tides():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tide_history (
        date TEXT PRIMARY KEY,
        moon_age REAL,
        tide TEXT
    )
    ''')
    
    start_date = datetime(2008, 1, 1)
    end_date = datetime(2035, 12, 31)
    
    current_date = start_date
    count = 0
    while current_date <= end_date:
        # 正午時点の月齢（日本時間）
        # 日本時間の12:00はUTCの03:00
        calc_time = current_date.strftime("%Y/%m/%d 03:00:00")
        d = ephem.Date(calc_time)
        try:
            prev_new_moon = ephem.previous_new_moon(d)
        except Exception:
            prev_new_moon = d
            
        moon_age = d - prev_new_moon
        tide = get_tide(moon_age)
        
        # DBに合わせるためYYYY-MM-DDフォーマット、一部DBがYYYY/MM/DDの可能性もあるので考慮
        # 現状の fishing_forecast.db の書式は 2026-02-24 のようなYYYY-MM-DD
        date_str = current_date.strftime("%Y-%m-%d")
        
        # スラッシュ表記も検索できるようにしておくが、主キーはハイフン
        cursor.execute('''
            INSERT OR REPLACE INTO tide_history (date, moon_age, tide)
            VALUES (?, ?, ?)
        ''', (date_str, float(moon_age), tide))
        
        current_date += timedelta(days=1)
        count += 1
        
    print("Patching calculated tides with actual official facility tide records...")
    cursor.execute('''
        UPDATE tide_history 
        SET tide = (
            SELECT tide FROM facility_logs 
            WHERE REPLACE(facility_logs.date, '/', '-') = tide_history.date 
            AND facility_logs.tide IS NOT NULL 
            AND facility_logs.tide != ''
            LIMIT 1
        ) 
        WHERE EXISTS (
            SELECT 1 FROM facility_logs 
            WHERE REPLACE(facility_logs.date, '/', '-') = tide_history.date 
            AND facility_logs.tide IS NOT NULL
            AND facility_logs.tide != ''
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Tide history generated successfully. {count} records calculated, facility data patched.")

if __name__ == "__main__":
    generate_tides()

