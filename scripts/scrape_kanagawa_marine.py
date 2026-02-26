#!/usr/bin/env python3
"""
神奈川県水産技術センター リアルタイム海況データ スクレイピング
データ取得元: https://kanagawapref.kansoku-data.net/

取得可能データ:
- 水温 (℃)
- 塩分 (PSU)
- 風向 (度)
- 風速 (cm/s)
- 風速 (Kt)

観測地点:
- 三崎瀬戸
- 城ヶ島沖西ブイ
- 城ヶ島沖東ブイ
- 相模湾中央ブイ
- 江の浦ブイ
"""

import urllib.request
from bs4 import BeautifulSoup
import re
from datetime import datetime
import sqlite3
import os
import time

# プロジェクトルートの data ディレクトリ
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "fishing_forecast.db")

# 観測地点のマッピング（文字化け対策）
LOCATION_MAP = {
    "三崎瀬戸": "misakiseto",
    "城ヶ島沖西ブイ": "jyougashimaw",
    "城ヶ島沖東ブイ": "jyougashimaoki",
    "相模湾中央ブイ": "sagamiwanc",
    "江の浦ブイ": "enoura"
}

def init_table():
    """
    神奈川県海洋環境データ用テーブルを作成
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS kanagawa_marine_data (
        date TEXT,
        time TEXT,
        location TEXT,
        water_temp REAL,
        salinity REAL,
        wind_direction REAL,
        wind_speed_cms REAL,
        wind_speed_kt REAL,
        PRIMARY KEY (date, time, location)
    )
    ''')

    conn.commit()
    conn.close()
    print("✅ Table initialized: kanagawa_marine_data")

def fetch_realtime_data():
    """
    リアルタイムデータページから最新の観測データを取得
    """
    url = "https://kanagawapref.kansoku-data.net/"

    try:
        # Shift_JISエンコーディングを指定してページを取得
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read()
        soup = BeautifulSoup(html, 'html.parser', from_encoding='shift_jis')

        # 最新観測データのテーブルを取得
        table = soup.find('table', class_='newdata')
        if not table:
            print("❌ Error: Could not find data table")
            return []

        records = []
        rows = table.find_all('tr')[1:]  # ヘッダー行をスキップ

        for row in rows:
            cols = row.find_all(['th', 'td'])
            if len(cols) < 8:
                continue

            location = cols[0].get_text(strip=True)
            date = cols[1].get_text(strip=True)
            time = cols[2].get_text(strip=True)
            water_temp = cols[3].get_text(strip=True).replace('-', '').strip()
            salinity = cols[4].get_text(strip=True).replace('-', '').strip()
            wind_dir = cols[5].get_text(strip=True).replace('-', '').strip()
            wind_speed_cms = cols[6].get_text(strip=True).replace('-', '').strip()
            wind_speed_kt = cols[7].get_text(strip=True).replace('-', '').strip()

            # YYYY/MM/DD 形式を YYYY-MM-DD に変換
            date_normalized = date.replace('/', '-')

            # 空文字列をNoneに変換
            def to_float_or_none(val):
                try:
                    return float(val) if val else None
                except ValueError:
                    return None

            record = {
                'date': date_normalized,
                'time': time,
                'location': location,
                'water_temp': to_float_or_none(water_temp),
                'salinity': to_float_or_none(salinity),
                'wind_direction': to_float_or_none(wind_dir),
                'wind_speed_cms': to_float_or_none(wind_speed_cms),
                'wind_speed_kt': to_float_or_none(wind_speed_kt)
            }

            records.append(record)
            print(f"📍 {location} | {date} {time} | 水温: {water_temp}℃ | 塩分: {salinity} PSU")

        return records

    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return []

def save_to_db(records):
    """
    取得したデータをSQLiteに保存
    """
    if not records:
        print("⚠️  No records to save")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    inserted = 0
    skipped = 0

    for record in records:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO kanagawa_marine_data
                (date, time, location, water_temp, salinity, wind_direction, wind_speed_cms, wind_speed_kt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record['date'],
                record['time'],
                record['location'],
                record['water_temp'],
                record['salinity'],
                record['wind_direction'],
                record['wind_speed_cms'],
                record['wind_speed_kt']
            ))

            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        except Exception as e:
            print(f"❌ Error saving record: {e}")
            skipped += 1

    conn.commit()
    conn.close()

    print(f"✅ Saved {inserted} records, skipped {skipped} duplicates")

def main():
    print("🌊 神奈川県水産技術センター 海洋環境データ スクレイピング開始")
    print("=" * 60)

    # テーブル初期化
    init_table()

    # リアルタイムデータ取得
    print("\n📡 Fetching latest marine data...")
    records = fetch_realtime_data()

    # データベースに保存
    print(f"\n💾 Saving {len(records)} records to database...")
    save_to_db(records)

    print("\n🎉 スクレイピング完了！")

if __name__ == "__main__":
    main()
