import sqlite3
import os

DB_PATH = 'data/fishing_forecast.db'

def init_db():
    if os.path.exists(DB_PATH):
        print(f"Database already exists at {DB_PATH}. Re-initializing...")
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 施設ログテーブル
    # facility + date で一意にする（重複登録防止）
    cursor.execute('''
    CREATE TABLE facility_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility TEXT NOT NULL,
        date TEXT NOT NULL,
        weather TEXT,
        water_temp REAL,
        tide TEXT,
        visitors INTEGER,
        sentence TEXT,
        UNIQUE(facility, date)
    )
    ''')
    cursor.execute('CREATE INDEX idx_facility_date ON facility_logs(facility, date)')

    # 施設釣果テーブル
    cursor.execute('''
    CREATE TABLE facility_catches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_id INTEGER NOT NULL,
        species TEXT NOT NULL,
        count INTEGER,
        size TEXT,
        places TEXT,
        FOREIGN KEY (log_id) REFERENCES facility_logs (id)
    )
    ''')
    cursor.execute('CREATE INDEX idx_facility_species ON facility_catches(species)')

    # 釣具屋ログテーブル
    # date + shop_name + place でほぼ一意に特定（店舗が同じ日に同じ場所のレポートを出すことは稀）
    cursor.execute('''
    CREATE TABLE shop_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        shop_name TEXT,
        area TEXT,
        place TEXT,
        category TEXT,
        weather TEXT,
        UNIQUE(date, shop_name, place)
    )
    ''')
    cursor.execute('CREATE INDEX idx_shop_date ON shop_logs(date)')

    # 釣具屋釣果テーブル
    cursor.execute('''
    CREATE TABLE shop_catches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_id INTEGER NOT NULL,
        species TEXT NOT NULL,
        count INTEGER,
        size TEXT,
        FOREIGN KEY (log_id) REFERENCES shop_logs (id)
    )
    ''')
    cursor.execute('CREATE INDEX idx_shop_species ON shop_catches(species)')

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
