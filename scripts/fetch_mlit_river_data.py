"""
国土交通省 水文水質データベースから河川流量データをCSVインポートするスクリプト。

使用方法:
    1. http://www1.river.go.jp/ にアクセス
    2. 荒川 笹目橋観測所の日次流量データをCSVダウンロード
    3. このスクリプトでDBにインポート:
       python scripts/fetch_mlit_river_data.py <csv_file_path>

CSVフォーマット (水文水質データベース標準):
    年月日, 流量(m³/s), ...
"""
import os
import sys
import csv
import re
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'fishing_forecast.db')


def init_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS river_discharge_history (
            date TEXT PRIMARY KEY,
            station_name TEXT,
            discharge REAL
        )
    ''')
    conn.commit()
    conn.close()


def import_csv(csv_path, station_name="笹目橋"):
    """水文水質データベースからダウンロードしたCSVをDBにインポート"""
    if not os.path.exists(csv_path):
        print(f"❌ ファイルが見つかりません: {csv_path}")
        return

    init_table()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    total = 0

    with open(csv_path, 'r', encoding='shift_jis', errors='replace') as f:
        reader = csv.reader(f)

        for row in reader:
            if len(row) < 2:
                continue

            # 日付パース (yyyy/mm/dd or yyyy-mm-dd 形式)
            date_str = row[0].strip()
            date_match = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
            if not date_match:
                continue

            try:
                d = datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
                d_str = d.strftime("%Y-%m-%d")
            except ValueError:
                continue

            # 流量パース
            try:
                discharge = float(row[1].strip())
            except (ValueError, IndexError):
                continue

            cursor.execute("""
                INSERT OR REPLACE INTO river_discharge_history (date, station_name, discharge)
                VALUES (?, ?, ?)
            """, (d_str, station_name, discharge))
            total += 1

    conn.commit()
    conn.close()
    print(f"🎉 完了！{station_name}から {total} レコードをインポートしました。")


def update_marine_forecast_table():
    """river_discharge_history のデータを marine_forecast_history に反映"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE marine_forecast_history
        SET river_discharge = (
            SELECT discharge FROM river_discharge_history
            WHERE river_discharge_history.date = marine_forecast_history.date
        )
        WHERE EXISTS (
            SELECT 1 FROM river_discharge_history
            WHERE river_discharge_history.date = marine_forecast_history.date
        )
    """)
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"  🔄 marine_forecast_history に {updated} レコードの河川流量を反映しました。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python scripts/fetch_mlit_river_data.py <csv_file_path> [station_name]")
        print("例: python scripts/fetch_mlit_river_data.py data/arakawa_discharge.csv 笹目橋")
        sys.exit(1)

    csv_path = sys.argv[1]
    station = sys.argv[2] if len(sys.argv) > 2 else "笹目橋"
    import_csv(csv_path, station)
    update_marine_forecast_table()
