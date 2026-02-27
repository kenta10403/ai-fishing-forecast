"""
DBテーブル名移行スクリプト (ワンショット)
openmeteo_marine_history → marine_forecast_history にリネーム
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'fishing_forecast.db')


def migrate():
    print("🔄 DBテーブル名移行を開始...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # テーブル存在確認
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='openmeteo_marine_history'")
    if cursor.fetchone():
        cursor.execute("ALTER TABLE openmeteo_marine_history RENAME TO marine_forecast_history")
        conn.commit()
        print("  ✅ openmeteo_marine_history → marine_forecast_history にリネーム完了")
    else:
        # 既にリネーム済み or テーブルが存在しない場合
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='marine_forecast_history'")
        if cursor.fetchone():
            print("  ℹ️ marine_forecast_history は既に存在します (移行済み)")
        else:
            # テーブルが存在しない場合は新規作成
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS marine_forecast_history (
                    date TEXT PRIMARY KEY,
                    wave_height_max REAL,
                    wave_direction_dominant INTEGER,
                    river_discharge REAL
                )
            ''')
            conn.commit()
            print("  🆕 marine_forecast_history テーブルを新規作成しました")

    conn.close()
    print("🎉 DBテーブル移行完了")


if __name__ == "__main__":
    migrate()
