import sqlite3
import urllib.request
from bs4 import BeautifulSoup
import time
from datetime import datetime
import os
import sys

# エリアごとの気象庁観測所ID設定
# prec_no: 都道府県ごとの番号, block_no: 観測所ごとの番号
STATIONS = {
    "神奈川県": {"prec_no": "46", "block_no": "47670"}, # 横浜
    "東京都":   {"prec_no": "44", "block_no": "47662"}, # 東京
    "千葉県":   {"prec_no": "45", "block_no": "47682"}, # 千葉
    "埼玉県":   {"prec_no": "43", "block_no": "47626"}, # 熊谷 (海なし・参考)
    "茨城県":   {"prec_no": "40", "block_no": "47629"}, # 水戸
}

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fishing_forecast.db")

def init_db(cursor):
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS weather_history (
        date TEXT,
        area TEXT,
        avg_temp REAL,
        max_temp REAL,
        min_temp REAL,
        avg_wind_speed REAL,
        max_wind_speed REAL,
        wind_direction TEXT,
        precipitation REAL,
        daylight_hours REAL,
        PRIMARY KEY (date, area)
    )
    ''')

def safe_float(val_str):
    try:
        # 気象庁のデータによくある "]", ")", "×" などの記号を除去
        clean_str = val_str.replace("]", "").replace(")", "").replace(" ", "").replace("×", "").replace("--", "")
        if not clean_str:
            return None
        return float(clean_str)
    except ValueError:
        return None

def fetch_month_data(area, year, month):
    station = STATIONS.get(area)
    if not station:
        return []
        
    url = f"https://www.data.jma.go.jp/obd/stats/etrn/view/daily_s1.php?prec_no={station['prec_no']}&block_no={station['block_no']}&year={year}&month={month}&day=&view="
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        html = urllib.request.urlopen(req).read()
    except Exception as e:
        print(f"Error fetching {area} {year}/{month}: {e}")
        return []
        
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table', class_='data2_s')
    
    if not tables:
        return []
        
    records = []
    rows = tables[0].find_all('tr')
    
    # 基本的にデータ行はインデックス4から始まる
    for row in rows[4:]:
        cols = row.find_all('td')
        if len(cols) < 15:
            continue
            
        day_str = cols[0].text.strip()
        if not day_str.isdigit():
            continue
            
        date_str = f"{year}-{month:02d}-{int(day_str):02d}"
        
        # JMAテーブルのカラムマッピング (観測所によって若干カラム数が変わることがあるが、主要都市はほぼ固定)
        # 1: 現地気圧, 2: 海面気圧, 3: 降水量合計, 4: 最大1時間雨量, 5: 最大10分間雨量
        # 6: 平均気温, 7: 最高気温, 8: 最低気温
        # 9: 平均湿度, 10: 最小湿度
        # 11: 平均風速, 12: 最大風速, 13: 最大風速風向, 14: 最大瞬間風速, 15: 最大瞬間風速風向
        # 16: 日照時間
        
        precip = safe_float(cols[3].text)
        avg_temp = safe_float(cols[6].text)
        max_temp = safe_float(cols[7].text)
        min_temp = safe_float(cols[8].text)
        avg_wind = safe_float(cols[11].text)
        max_wind = safe_float(cols[12].text)
        wind_dir = cols[13].text.strip().replace("]", "").replace(")", "").replace(" ", "")
        if wind_dir in ["--", "×", "静穏"]:
            wind_dir = "無風"
            
        # 16番目が日照時間（無い場合もある）
        daylight = None
        if len(cols) > 16:
            daylight = safe_float(cols[16].text)
            
        records.append((
            date_str, area, avg_temp, max_temp, min_temp, 
            avg_wind, max_wind, wind_dir, precip, daylight
        ))
        
    return records

def download_historical_weather(start_year=2009, end_year=None):
    if end_year is None:
        end_year = datetime.now().year
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    init_db(cursor)
    
    # 対象エリア（関東の海沿い・主要釣り場）
    target_areas = ["神奈川県", "東京都", "千葉県", "茨城県"]
    
    total_inserted = 0
    
    for area in target_areas:
        print(f"=== Fetching data for {area} ({start_year} - {end_year}) ===")
        for year in range(start_year, end_year + 1):
            
            # 今年（未来の月）はスキップするための処理
            current_month = datetime.now().month if year == datetime.now().year else 12
            
            for month in range(1, current_month + 1):
                sys.stdout.write(f"\rDownloading {year}-{month:02d}...")
                sys.stdout.flush()
                
                records = fetch_month_data(area, year, month)
                if records:
                    cursor.executemany('''
                        INSERT OR REPLACE INTO weather_history (
                            date, area, avg_temp, max_temp, min_temp, 
                            avg_wind_speed, max_wind_speed, wind_direction, precipitation, daylight_hours
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', records)
                    conn.commit()
                    total_inserted += len(records)
                
                # 気象庁サーバーに負荷をかけないよう必ず1秒待機
                time.sleep(1)
            print()
            
    conn.close()
    print(f"\nAll downloads completed! Processed {total_inserted} days of weather data.")

if __name__ == "__main__":
    download_historical_weather(2009, datetime.now().year)
