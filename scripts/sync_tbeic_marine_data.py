#!/usr/bin/env python3
"""
東京湾環境情報センター (TBEIC) 水質連続観測データ 同期スクリプト

TBEICのPOSTエンドポイントから15分間隔の水質データを取得し、
日次集計（平均・最高・最低）を行って tokyo_bay_marine_data テーブルに格納します。
"""

import urllib.request
import urllib.parse
import sqlite3
import os
import time
import pandas as pd
import io
from datetime import datetime, timedelta

# プロジェクトルート
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "fishing_forecast.db")

# TBEIC 設定
TBEIC_URL = "https://www.tbeic.go.jp/MonitoringPost/ViewGraph/downLoadObservedCSVData"
BUOY_MAP = {
    "01": "検見川沖",
    "03": "浦安沖",
    "02": "川崎人工島",
    "04": "千葉港口第一号灯標",
}

def init_db():
    """テーブルがなければ作成（既存のスキーマに合わせる）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tokyo_bay_marine_data (
        date TEXT,
        location TEXT,
        location_code TEXT,
        water_temp REAL,
        salinity REAL,
        do_level REAL,
        cod REAL,
        total_nitrogen REAL,
        total_phosphorus REAL,
        transparency REAL,
        is_kuroshio_meander INTEGER DEFAULT 0,
        fiscal_year INTEGER,
        data_source TEXT,
        PRIMARY KEY (date, location_code)
    )
    ''')
    conn.commit()
    conn.close()

def fetch_tbeic_csv(buoy_id, start_date, end_date):
    """TBEICからCSVデータを取得"""
    params = {
        "buoyId": buoy_id,
        "sDateTimeId": start_date.strftime("%Y%m%d0000"),
        "eDateTimeId": end_date.strftime("%Y%m%d2359"),
        "downloadItems": "waterTemperature,salinity,do,"
    }
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(TBEIC_URL, data=data, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        # TLS検証エラー対策 (環境によって必要)
        import ssl
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=60, context=context) as response:
            return response.read().decode("cp932", errors="replace")
    except Exception as e:
        print(f"  ❌ Error fetching data for {buoy_id}: {e}")
        return None

def process_csv_to_daily(csv_text, buoy_name, buoy_id):
    """15分間隔のCSVを日次平均に集約"""
    if not csv_text or len(csv_text.strip()) == 0:
        return []

    # ヘッダーなしCSVとして読み込み
    # TBEICのCSV構成: 日時, 上層(水温,塩分,DO,pH), 中層(...), 下層(...)
    # 1行目が「年月日時分, ...」となっているためスキップする
    try:
        df = pd.read_csv(io.StringIO(csv_text), header=None, skiprows=1)
        if df.empty:
            return []
        
        df.columns = ['datetime', 'temp_u', 'salt_u', 'do_u', 'ph_u', 'temp_m', 'salt_m', 'do_m', 'ph_m', 'temp_l', 'salt_l', 'do_l', 'ph_l']
        
        # 異常値(99999.99)をNaNに変換
        df.replace(99999.99, pd.NA, inplace=True)
        
        # 日時パース (形式: 2024/02/01 02:15)
        df['datetime'] = pd.to_datetime(df['datetime'], format='%Y/%m/%d %H:%M', errors='coerce')
        df = df.dropna(subset=['datetime'])
        df['date'] = df['datetime'].dt.strftime('%Y-%m-%d')
        
        # 数値変換
        numeric_cols = ['temp_u', 'salt_u', 'do_u']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 日次集約 (平均)
        daily = df.groupby('date').agg({
            'temp_u': 'mean',
            'salt_u': 'mean',
            'do_u': 'mean'
        }).reset_index()
        
        records = []
        for _, row in daily.iterrows():
            if pd.isna(row['temp_u']) and pd.isna(row['salt_u']) and pd.isna(row['do_u']):
                continue
                
            dt = datetime.strptime(row['date'], '%Y-%m-%d')
            records.append({
                'date': row['date'],
                'location': buoy_name,
                'location_code': buoy_id,
                'water_temp': row['temp_u'],
                'salinity': row['salt_u'],
                'do_level': row['do_u'],
                'fiscal_year': dt.year if dt.month >= 4 else dt.year - 1,
                'data_source': 'tbeic_continuous'
            })
        return records
    except Exception as e:
        print(f"  ❌ Error processing CSV: {e}")
        return []

def save_to_db(records):
    """DBに保存 (既存データは上書き推奨)"""
    if not records:
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 黒潮大蛇行判定ロジック
    KUROSHIO_START = datetime(2017, 8, 1)
    KUROSHIO_END = datetime(2025, 4, 30)

    inserted = 0
    for r in records:
        dt = datetime.strptime(r['date'], '%Y-%m-%d')
        is_meander = 1 if KUROSHIO_START <= dt <= KUROSHIO_END else 0
        
        cursor.execute('''
            INSERT OR REPLACE INTO tokyo_bay_marine_data
            (date, location, location_code, water_temp, salinity, do_level, is_kuroshio_meander, fiscal_year, data_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            r['date'], r['location'], r['location_code'],
            r['water_temp'], r['salinity'], r['do_level'],
            is_meander, r['fiscal_year'], r['data_source']
        ))
        inserted += cursor.rowcount

    conn.commit()
    conn.close()
    return inserted

def sync_all(start_year=2010):
    """全地点・全期間を同期"""
    init_db()
    today = datetime.now()
    
    for buoy_id, buoy_name in BUOY_MAP.items():
        print(f"🚢 同期開始: {buoy_name} ({buoy_id})")
        
        current_start = datetime(start_year, 1, 1)
        while current_start < today:
            # 1ヶ月単位で取得
            next_month = current_start.replace(day=28) + timedelta(days=4)
            current_end = next_month.replace(day=1) - timedelta(days=1)
            if current_end > today:
                current_end = today
            
            print(f"  📅 {current_start.strftime('%Y-%m')} 取得中...")
            csv_text = fetch_tbeic_csv(buoy_id, current_start, current_end)
            records = process_csv_to_daily(csv_text, buoy_name, buoy_id)
            
            if records:
                num = save_to_db(records)
                print(f"  ✅ {len(records)} 日分のデータを保存しました。")
            
            current_start = current_end + timedelta(days=1)
            time.sleep(1)  # サーバー負荷軽減

if __name__ == "__main__":
    import sys
    # 引数で開始年を指定可能
    start_y = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    sync_all(start_y)
