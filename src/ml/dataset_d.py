import json
import os

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

TARGET_SPECIES_LIST = [
    "アジ", "イワシ", "サバ", "スズキ", "シーバス", "クロダイ", "チヌ",
    "カサゴ", "メバル", "シロギス", "タコ", "イナダ", "ワラサ", "ブリ", "サワラ"
]

import sqlite3

DB_PATH = os.path.join(DATA_DIR, "fishing_forecast.db")

def load_trend_data() -> pd.DataFrame:
    """
    SQLiteからデータをロードし、日次・エリア別にグルーピングしてトレンド指数を算出する。
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database not found at {DB_PATH}. Run init_db.py and import_json_to_db.py first.")

    conn = sqlite3.connect(DB_PATH)
    
    # 施設データと釣具屋データをUNIONで結合して取得
    # 名寄せ（シーバス→スズキ等）もSQL側で処理可能な範囲で行う
    query = f"""
    SELECT 
        l.date, 
        l.facility as shop, 
        '神奈川県' as area, -- 施設は基本神奈川
        l.weather, 
        l.water_temp, 
        l.visitors, 
        1.0 as weight,
        TRUE as is_facility,
        c.species,
        c.count as counts,
        1 as report
    FROM facility_logs l
    JOIN facility_catches c ON l.id = c.log_id
    
    UNION ALL
    
    SELECT 
        l.date, 
        l.shop_name as shop, 
        l.area, 
        l.weather, 
        NULL as water_temp, 
        0 as visitors, 
        0.3 as weight,
        FALSE as is_facility,
        c.species,
        c.count as counts,
        1 as report
    FROM shop_logs l
    JOIN shop_catches c ON l.id = c.log_id
    WHERE l.area IN ('東京都', '神奈川県', '千葉県', '埼玉県', '茨城県', '栃木県', '群馬県')
    AND l.category = 'sea'
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        return df

    # --- 名寄せとフィルタリング (Python側) ---
    def normalize_species(name):
        if not name: return None
        for sp in TARGET_SPECIES_LIST:
            if sp in name:
                if sp == "シーバス": return "スズキ"
                if sp == "チヌ": return "クロダイ"
                if sp in ["ワラサ", "ブリ"]: return "イナダ"
                return sp
        return None

    df['species'] = df['species'].apply(normalize_species)
    df = df.dropna(subset=['species'])

    df['water_temp'] = pd.to_numeric(df['water_temp'], errors='coerce')

    # 日付型変換
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])

    # グルーピング集計
    grouped = df.groupby(['date', 'area', 'weather', 'species', 'is_facility', 'weight']).agg({
        'report': 'sum',
        'counts': 'sum',
        'visitors': 'max',
        'water_temp': 'mean'
    }).reset_index()

    # トレンド指標の算出
    def calc_trend_score(row):
        if row['is_facility'] and row['visitors'] > 0:
            return (row['counts'] / row['visitors']) * 100 * row['weight']
        else:
            return (row['report'] * 10 + row['counts']) * row['weight']

    grouped['trend_score'] = grouped.apply(calc_trend_score, axis=1)

    # --- バイアス補正 ---
    q1 = grouped['trend_score'].quantile(0.05)
    q3 = grouped['trend_score'].quantile(0.95)
    iqr = q3 - q1
    lower_bound = max(0, q1 - 1.5 * iqr)
    upper_bound = q3 + 1.5 * iqr
    
    grouped = grouped[(grouped['trend_score'] >= lower_bound) & (grouped['trend_score'] <= upper_bound)].copy()

    # 曜日バイアスの正規化
    grouped['day_of_week'] = grouped['date'].dt.dayofweek
    weekday_mean = grouped.groupby('day_of_week')['trend_score'].mean()
    overall_mean = grouped['trend_score'].mean()
    if overall_mean > 0:
        weekday_factor = weekday_mean / overall_mean
        grouped['trend_score'] = grouped.apply(
            lambda row: row['trend_score'] / weekday_factor.get(row['day_of_week'], 1.0)
            if pd.notna(row['day_of_week']) else row['trend_score'],
            axis=1
        )

    # 重複排除
    grouped = grouped.sort_values('weight', ascending=False).drop_duplicates(
        subset=['date', 'area', 'species'], keep='first'
    ).reset_index(drop=True)

    return grouped

def preprocess_trend_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    特徴量エンジニアリングと前処理（パターンD トレンド用）
    """
    if df.empty:
        raise ValueError("提供されたデータフレームが空です")

    df['month'] = df['date'].dt.month
    df['day'] = df['date'].dt.day
    df['day_of_week'] = df['date'].dt.dayofweek

    def calc_period(row):
        if pd.isna(row['month']) or pd.isna(row['day']):
            return 1
        m = int(row['month'])
        d = int(row['day'])
        part = 0 if d <= 10 else 1 if d <= 20 else 2
        return (m - 1) * 3 + part + 1

    df['period_of_year'] = df.apply(calc_period, axis=1)

    def simplify_weather(w):
        if pd.isna(w): return "不明"
        if "晴" in w: return "晴れ"
        if "雨" in w: return "雨"
        if "曇" in w: return "曇り"
        return "その他"

    df['weather_simple'] = df['weather'].apply(simplify_weather)

    features = ['period_of_year', 'day_of_week', 'area', 'weather_simple', 'species', 'water_temp']
    X = df[features]
    y = df['trend_score']

    # 水温の欠損値補完（その「旬」の平均水温などで埋めるのが理想だが、一旦全体平均または0）
    X['water_temp'] = X['water_temp'].fillna(X['water_temp'].mean() if not X['water_temp'].isna().all() else 0)

    # One-Hot Encoding
    X = pd.get_dummies(X, columns=['area', 'weather_simple', 'species'], drop_first=True)
    X.fillna(0, inplace=True)

    return X, y

if __name__ == "__main__":
    df_raw = load_trend_data()
    print(f"集計後のレコード件数: {len(df_raw)}")
    if not df_raw.empty:
        print(df_raw.head())
        X, y = preprocess_trend_data(df_raw)
        print("X shape:", X.shape)
        print("y shape:", y.shape)
