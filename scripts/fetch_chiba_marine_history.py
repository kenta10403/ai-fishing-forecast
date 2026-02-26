#!/usr/bin/env python3
"""
千葉県 東京湾内湾 公共用水域水質測定結果 過去データ取得スクリプト

対象期間: 2009年〜現在
データソース: 千葉県環境生活部水質保全課
URL: https://www.pref.chiba.lg.jp/suiho/kasentou/koukyouyousui/data/

取得データ:
- 水温 (Water Temperature)
- 塩分 (Salinity)
- DO (溶存酸素量 - Dissolved Oxygen)
- COD, 全窒素, 全リン など

観測地点:
- 浦安沖
- 検見川沖
- 千葉港口
- その他東京湾内湾の複数地点
"""

import urllib.request
import csv
import sqlite3
import os
import time
from datetime import datetime
import io

# プロジェクトルート
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "fishing_forecast.db")
DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, "data", "chiba_marine_csv")

# 黒潮大蛇行期間（2017年8月〜2025年4月）
KUROSHIO_MEANDER_START = datetime(2017, 8, 1)
KUROSHIO_MEANDER_END = datetime(2025, 4, 30)

# ダウンロード対象年度
# 平成21年(2009年) 〜 令和6年(2024年)
YEARS_CONFIG = [
    # 平成年度 (2009-2015) - 内湾海域データ
    {"year": 2009, "file": "09y_s_naiwan.csv", "era": "h"},
    {"year": 2010, "file": "10y_s_naiwan.csv", "era": "h"},
    {"year": 2011, "file": "11y_s_naiwan.csv", "era": "h"},
    {"year": 2012, "file": "12y_s_naiwan.csv", "era": "h"},
    {"year": 2013, "file": "13y_s_naiwan.csv", "era": "h"},
    {"year": 2014, "file": "14y_s_naiwan.csv", "era": "h"},
    {"year": 2015, "file": "15y_s_naiwan.csv", "era": "h"},
    # 平成28年〜30年 (2016-2018) - 海域データ
    {"year": 2016, "file": "H28-sea.csv", "era": "h"},
    {"year": 2017, "file": "h29-sea.csv", "era": "h"},
    {"year": 2018, "file": "h30-08-sea.csv", "era": "h"},
    # 令和年度 (2019-) - 海域データ
    {"year": 2019, "file": "r1-08-sea.csv", "era": "r"},
    {"year": 2020, "file": "r2-08-sea.csv", "era": "r"},
    {"year": 2021, "file": "r3-08-sea.csv", "era": "r"},
    {"year": 2022, "file": "r4-08-sea.csv", "era": "r"},
    {"year": 2023, "file": "r5-08-sea.csv", "era": "r"},
    {"year": 2024, "file": "r6-08-sea.csv", "era": "r"},
]

def init_table():
    """
    東京湾内湾水質データ用テーブルを作成
    """
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
        data_source TEXT DEFAULT 'chiba_prefecture',
        PRIMARY KEY (date, location_code)
    )
    ''')

    conn.commit()
    conn.close()
    print("✅ Table initialized: tokyo_bay_marine_data")

def is_kuroshio_meander_period(date_str):
    """
    指定された日付が黒潮大蛇行期間内かどうか判定
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return 1 if KUROSHIO_MEANDER_START <= date_obj <= KUROSHIO_MEANDER_END else 0
    except:
        return 0

def download_csv(year_config):
    """
    CSVファイルをダウンロード
    """
    base_url = "https://www.pref.chiba.lg.jp/suiho/kasentou/koukyouyousui/data/documents/"
    url = base_url + year_config["file"]

    try:
        print(f"  📥 Downloading {year_config['year']} ({year_config['file']})...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=30)

        # CP932でデコード (機種依存文字などはreplaceで回避)
        content = response.read().decode('cp932', errors='replace')

        # ファイルに保存
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        local_path = os.path.join(DOWNLOAD_DIR, year_config["file"])
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"  ✅ Downloaded to {local_path}")
        return local_path

    except Exception as e:
        print(f"  ❌ Error downloading {year_config['year']}: {e}")
        return None

def parse_csv(file_path, fiscal_year):
    """
    CSVファイルをパースしてデータ抽出
    千葉県のCSVは複雑な構造なので柔軟に対応
    """
    records = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # CSVとして読み込み
        csv_reader = csv.reader(io.StringIO(content))
        rows = list(csv_reader)

        # ヘッダー行を探す
        header_row_idx = None
        for idx, row in enumerate(rows):
            # "調査地点" or "地点名" or "測定地点" などが含まれる行を探す
            if any("地点" in str(cell) for cell in row):
                header_row_idx = idx
                break

        if header_row_idx is None:
            print(f"  ⚠️  Could not find header row in {file_path}")
            return records

        headers = rows[header_row_idx]

        # カラムインデックスを特定
        date_idx = None
        year_idx = None
        month_day_idx = None
        location_idx = None
        location_code_idx = None
        water_temp_idx = None
        salinity_idx = None
        do_idx = None
        cod_idx = None
        nitrogen_idx = None
        phosphorus_idx = None
        transparency_idx = None

        for idx, header in enumerate(headers):
            h = str(header).strip()
            if "測定年月日" in h or h == "年月日" or h == "年月日 ":
                date_idx = idx
            elif "採取年" in h:
                year_idx = idx
            elif "採取月日" in h:
                month_day_idx = idx
            elif "地点名" in h or "調査地点" in h:
                location_idx = idx
            elif "地点コード" in h or "測定地点コード" in h:
                location_code_idx = idx
            elif "水温" in h:
                water_temp_idx = idx
            elif "塩分" in h or "塩分濃度" in h:
                salinity_idx = idx
            elif "DO" in h or "溶存酸素" in h:
                do_idx = idx
            elif "COD" in h:
                cod_idx = idx
            elif "全窒素" in h or "T-N" in h:
                nitrogen_idx = idx
            elif "全りん" in h or "全リン" in h or "T-P" in h:
                phosphorus_idx = idx
            elif "透明度" in h:
                transparency_idx = idx

        # データ行を処理
        for row in rows[header_row_idx + 1:]:
            has_date = (date_idx is not None and date_idx < len(row)) or (year_idx is not None and year_idx < len(row) and month_day_idx is not None and month_day_idx < len(row))
            if not has_date:
                continue

            # 日付取得
            date_str = ""
            if date_idx is not None and date_idx < len(row):
                d_val = str(row[date_idx]).strip()
                if d_val and d_val != "":
                    # 20240408 => 2024-04-08
                    if len(d_val) == 8 and d_val.isdigit():
                        date_str = f"{d_val[:4]}-{d_val[4:6]}-{d_val[6:]}"
                    elif "/" in d_val:
                        try:
                            parts = d_val.split("/")
                            if len(parts) == 3:
                                date_str = f"{parts[0].zfill(4)}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
                        except:
                            pass
            
            if not date_str and year_idx is not None and month_day_idx is not None:
                y_val = str(row[year_idx]).strip()
                md_val = str(row[month_day_idx]).strip() # e.g. "409" for April 9
                if y_val.isdigit() and md_val.isdigit():
                    m = md_val[:-2].zfill(2)
                    d = md_val[-2:].zfill(2)
                    date_str = f"{y_val}-{m}-{d}"
            
            if not date_str:
                continue

            # 地点名・コード
            location = row[location_idx].strip() if location_idx is not None and location_idx < len(row) else ""
            location_code = row[location_code_idx].strip() if location_code_idx is not None and location_code_idx < len(row) else location

            if not location and not location_code:
                continue

            # 東京湾内湾のデータのみフィルタ (海域データには千葉県全域の海が含まれるため)
            # 水域名称や地点名称に「東京湾」「内湾」「盤洲」「木更津」などが含まれるか、そもそも15y_s_naiwan.csvのように全体が内湾データか判断
            is_tokyo_bay = False
            raw_row_text = ",".join([str(c) for c in row]).lower()
            if "東京湾" in raw_row_text or "幕張" in raw_row_text or "検見川" in raw_row_text or "千葉港" in raw_row_text or "姉崎" in raw_row_text or "浦安" in raw_row_text or "盤洲" in raw_row_text or "三番瀬" in raw_row_text or "木更津" in raw_row_text:
                is_tokyo_bay = True
            
            # 平成27年度以前のファイルはすべて内湾海域データ
            if fiscal_year <= 2015:
                is_tokyo_bay = True

            if not is_tokyo_bay:
                continue

            # 数値データ抽出
            def safe_float(val):
                try:
                    v = str(val).strip().replace(",", "")
                    if v in ["", "-", "×", "＜"]:
                        return None
                    # "<0.5" のような表記を処理
                    if v.startswith("<") or v.startswith("＜"):
                        v = v[1:]
                    return float(v) if v else None
                except:
                    return None

            water_temp = safe_float(row[water_temp_idx]) if water_temp_idx is not None and water_temp_idx < len(row) else None
            salinity = safe_float(row[salinity_idx]) if salinity_idx is not None and salinity_idx < len(row) else None
            do_level = safe_float(row[do_idx]) if do_idx is not None and do_idx < len(row) else None
            cod = safe_float(row[cod_idx]) if cod_idx is not None and cod_idx < len(row) else None
            nitrogen = safe_float(row[nitrogen_idx]) if nitrogen_idx is not None and nitrogen_idx < len(row) else None
            phosphorus = safe_float(row[phosphorus_idx]) if phosphorus_idx is not None and phosphorus_idx < len(row) else None
            transparency = safe_float(row[transparency_idx]) if transparency_idx is not None and transparency_idx < len(row) else None

            # 黒潮大蛇行フラグ
            is_meander = is_kuroshio_meander_period(date_str)

            record = {
                'date': date_str,
                'location': location,
                'location_code': location_code,
                'water_temp': water_temp,
                'salinity': salinity,
                'do_level': do_level,
                'cod': cod,
                'total_nitrogen': nitrogen,
                'total_phosphorus': phosphorus,
                'transparency': transparency,
                'is_kuroshio_meander': is_meander,
                'fiscal_year': fiscal_year
            }

            records.append(record)

        print(f"  📊 Parsed {len(records)} records from {fiscal_year}")
        return records

    except Exception as e:
        print(f"  ❌ Error parsing {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return records

def save_to_db(records):
    """
    データをDBに保存
    """
    if not records:
        print("  ⚠️  No records to save")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    inserted = 0
    updated = 0

    for record in records:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO tokyo_bay_marine_data
                (date, location, location_code, water_temp, salinity, do_level, cod,
                 total_nitrogen, total_phosphorus, transparency, is_kuroshio_meander, fiscal_year, data_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record['date'],
                record['location'],
                record['location_code'],
                record['water_temp'],
                record['salinity'],
                record['do_level'],
                record['cod'],
                record['total_nitrogen'],
                record['total_phosphorus'],
                record['transparency'],
                record['is_kuroshio_meander'],
                record['fiscal_year'],
                'chiba_prefecture'
            ))

            if cursor.rowcount > 0:
                inserted += 1

        except Exception as e:
            print(f"  ❌ Error saving record: {e}")

    conn.commit()
    conn.close()

    print(f"  ✅ Saved {inserted} records to database")

def main():
    print("🌊 千葉県 東京湾内湾 過去水質データ取得開始")
    print(f"📅 対象期間: 2009年〜2024年 (16年分)")
    print(f"🌀 黒潮大蛇行期間: 2017年8月〜2025年4月")
    print("=" * 70)

    # テーブル初期化
    init_table()

    # 年度ごとにダウンロード・パース・保存
    total_records = 0

    for year_config in YEARS_CONFIG:
        print(f"\n📆 Processing {year_config['year']} 年度...")

        # ダウンロード
        file_path = download_csv(year_config)
        if not file_path:
            continue

        # パース
        time.sleep(1)  # サーバー負荷軽減
        records = parse_csv(file_path, year_config['year'])

        # DB保存
        if records:
            save_to_db(records)
            total_records += len(records)

    print("\n" + "=" * 70)
    print(f"🎉 完了！合計 {total_records} レコードを取得・保存しました！")
    print(f"💾 DB: {DB_PATH}")
    print(f"📁 CSV保存先: {DOWNLOAD_DIR}")

if __name__ == "__main__":
    main()
