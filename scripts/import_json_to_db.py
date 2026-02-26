import json
import sqlite3
import os
import sys

DB_PATH = 'data/fishing_forecast.db'

def import_facility_data(conn):
    facs = ['honmoku', 'daikoku', 'isogo', 'ichihara']
    cursor = conn.cursor()
    print("Importing facility data (with de-duplication)...")
    
    for fac in facs:
        path = f'data/{fac}_2024_to_present.json'
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue
        
        print(f"Processing {fac}...")
        with open(path, 'r') as f:
            raw = json.load(f)
            data = raw.get('data', []) if isinstance(raw, dict) else raw
            
        for row in data:
            date = row.get('date')
            if not date: continue
            
            # INSERT OR IGNORE を使うことで、UNIQUE制約に抵触した（既に存在する）場合は何もしない
            cursor.execute('''
                INSERT OR IGNORE INTO facility_logs (facility, date, weather, water_temp, tide, visitors, sentence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                fac,
                date,
                row.get('weather'),
                row.get('waterTemp'),
                row.get('tide'),
                row.get('visitors'),
                row.get('sentence')
            ))
            
            # 無視された場合はrowcountが1にならないので、釣果のインサートをスキップ
            if cursor.rowcount == 0:
                continue
                
            log_id = cursor.lastrowid
            
            for catch in row.get('catches', []):
                places_raw = catch.get('place')
                places = ",".join(places_raw) if isinstance(places_raw, list) else str(places_raw) if places_raw else None
                
                cursor.execute('''
                    INSERT INTO facility_catches (log_id, species, count, size, places)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    log_id,
                    catch.get('name'),
                    catch.get('count'),
                    catch.get('size'),
                    places
                ))
    conn.commit()

def import_shop_data(conn, file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
    
    cursor = conn.cursor()
    print(f"Importing shop data from {file_path} (with de-duplication)...")
    
    with open(file_path, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error decoding {file_path}: {e}")
            return
        
    for i, row in enumerate(data):
        date = row.get('date')
        if not date: continue
        
        # date, shop_name, place の組み合わせで UNIQUE 制約をかけている
        cursor.execute('''
            INSERT OR IGNORE INTO shop_logs (date, shop_name, area, place, category, weather)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            date,
            row.get('shopName'),
            row.get('area'),
            row.get('place'),
            row.get('category'),
            row.get('weather')
        ))
        
        if cursor.rowcount == 0:
            continue
            
        log_id = cursor.lastrowid
        
        for catch in row.get('catches', []):
            cursor.execute('''
                INSERT INTO shop_catches (log_id, species, count, size)
                VALUES (?, ?, ?, ?)
            ''', (
                log_id,
                catch.get('name'),
                catch.get('count'),
                catch.get('size')
            ))
        
        if i % 1000 == 0:
            print(f"Processed {i} shop logs...", end='\r')
            conn.commit()
    
    conn.commit()
    print(f"\nCompleted {file_path}")

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print("Database not found. Please run init_db.py first.")
        sys.exit(1)
        
    conn = sqlite3.connect(DB_PATH)
    
    import_facility_data(conn)
    
    # 複数ファイルにまたがって重複があっても、UNIQUE制約と INSERT OR IGNORE で弾かれる
    shop_files = [
        'data/casting_choka_full.json',
        'data/casting_choka_resume.json',
        'data/johshuya_history.json'
    ]
    
    for sf in shop_files:
        import_shop_data(conn, sf)
        
    print("Optimizing database...")
    conn.execute("VACUUM")
    conn.close()
    print("Migration complete!")
