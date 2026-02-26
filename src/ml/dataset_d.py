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
        COALESCE(wh.avg_temp, l.water_temp) as water_temp, -- 水温の代わりに気温を使用可能に
        th.tide,
        wh.avg_wind_speed,
        wh.max_wind_speed,
        wh.wind_direction,
        wh.precipitation,
        wh.avg_temp,
        l.visitors, 
        1.0 as weight,
        TRUE as is_facility,
        c.species,
        c.count as counts,
        1 as report
    FROM facility_logs l
    JOIN facility_catches c ON l.id = c.log_id
    LEFT JOIN tide_history th ON th.date = REPLACE(l.date, '/', '-')
    LEFT JOIN weather_history wh ON wh.date = REPLACE(l.date, '/', '-') AND wh.area = '神奈川県'
    
    UNION ALL
    
    SELECT 
        l.date, 
        l.shop_name as shop, 
        l.area, 
        wh.avg_temp as water_temp, -- 水温がないので気温をフォールバックに 
        th.tide,
        wh.avg_wind_speed,
        wh.max_wind_speed,
        wh.wind_direction,
        wh.precipitation,
        wh.avg_temp,
        0 as visitors, 
        0.3 as weight,
        FALSE as is_facility,
        c.species,
        c.count as counts,
        1 as report
    FROM shop_logs l
    JOIN shop_catches c ON l.id = c.log_id
    LEFT JOIN tide_history th ON th.date = REPLACE(l.date, '/', '-')
    LEFT JOIN weather_history wh ON wh.date = REPLACE(l.date, '/', '-') AND wh.area = l.area
    WHERE l.area IN ('東京都', '神奈川県', '千葉県', '茨城県') -- JMAデータ取得済みの主要4県に絞る
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

    df['tide'] = df['tide'].fillna('不明')
    df['wind_direction'] = df['wind_direction'].fillna('不明')
    
    # 連続値の欠損補完（全体平均）
    for col in ['avg_wind_speed', 'max_wind_speed', 'precipitation', 'avg_temp']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        df[col] = df[col].fillna(df[col].mean())

    # グルーピング集計
    grouped = df.groupby(['date', 'area', 'tide', 'wind_direction', 'species', 'is_facility', 'weight']).agg({

        'report': 'sum',
        'counts': 'sum',
        'visitors': 'max',
        'water_temp': 'mean',
        'avg_wind_speed': 'mean',
        'max_wind_speed': 'mean',
        'precipitation': 'mean',
        'avg_temp': 'mean'
    }).reset_index()

    # トレンド指標の算出
    def calc_trend_score(row):
        base_score = 0
        if row['is_facility'] and row['visitors'] > 0:
            # 入場者が多いほど「釣果を報告せずに帰る人」が増えるという推測に基づく補正
            # 入場者1000人を上限として、最大20%のスコア上方修正を入れる
            crowd_bonus = 1.0 + min(row['visitors'] / 1000.0, 1.0) * 0.2
            base_score = (row['counts'] / row['visitors']) * crowd_bonus
        else:
            base_score = (row['report'] * 1 + row['counts'] * 0.1)

        # ベーススコア × 信頼度(weight)
        return base_score * 100 * row['weight']

    grouped['trend_score'] = grouped.apply(calc_trend_score, axis=1)

    # --- バブルデータ（上振れ）のクリッピング ---
    # 下振れのカットは廃止（渋い日も「学習すべき事実」として扱うため）
    q1 = grouped['trend_score'].quantile(0.10)
    q3 = grouped['trend_score'].quantile(0.90)
    iqr = q3 - q1
    upper_bound = q3 + 1.5 * iqr
    
    # 上限を超えたスコアは上限値に丸める（カットして消さずに残す）
    grouped['trend_score'] = grouped['trend_score'].clip(upper=upper_bound)

    # 重複排除
    grouped = grouped.sort_values('weight', ascending=False).drop_duplicates(
        subset=['date', 'area', 'species'], keep='first'
    ).reset_index(drop=True)

    return grouped

def preprocess_trend_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    特徴量エンジニアリングと前処理（パターンD トレンド用）
    戻り値: 特徴量(X), 目的変数(y), サンプル重み(sample_weight)
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

    def classify_wind(w_dir):
        if pd.isna(w_dir) or w_dir == "不明": return "不明"
        if "北" in w_dir: return "北風"
        if "南" in w_dir: return "南風"
        if "東" in w_dir: return "東風"
        if "西" in w_dir: return "西風"
        return "無風"
        
    df['wind_dir_simple'] = df['wind_direction'].apply(classify_wind)

    features = [
        'period_of_year', 'day_of_week', 'area', 
        'wind_dir_simple', 'tide', 'species', 
        'water_temp', 'avg_wind_speed', 'max_wind_speed', 
        'precipitation', 'avg_temp'
    ]
    
    X = df[features]
    y = df['trend_score']
    sample_weight = df['weight'] # AIモデルの学習時の重要度として使用

    # 水温の欠損値補完（その「旬」の平均水温などで埋めるのが理想だが、一旦全体平均または0）
    X['water_temp'] = X['water_temp'].fillna(X['water_temp'].mean() if not X['water_temp'].isna().all() else 0)

    # One-Hot Encoding
    X = pd.get_dummies(X, columns=['area', 'wind_dir_simple', 'tide', 'species'], drop_first=True)
    X.fillna(0, inplace=True)

    return X, y, sample_weight

if __name__ == "__main__":
    df_raw = load_trend_data()
    print(f"集計後のレコード件数: {len(df_raw)}")
    if not df_raw.empty:
        print(df_raw.head())
        X, y, sample_weight = preprocess_trend_data(df_raw)
        print("X shape:", X.shape)
        print("y shape:", y.shape)
        print("sample_weight shape:", sample_weight.shape)
