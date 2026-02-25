import json
import os
import pandas as pd
from typing import List, Optional, Tuple

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

# 予測対象とする主要な魚種
TARGET_SPECIES_LIST = [
    "アジ", "イワシ", "サバ", "スズキ", "クロダイ",
    "カサゴ", "メバル", "シロギス", "タコ", "イナダ"
]

def load_data_b(
    include_files: Optional[List[str]] = None,
    exclude_files: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    指定されたJSONファイル群をロードし、DataFrameに変換して返す（パターンB用）。
    各主要魚種の釣果数をそれぞれのカラムとして保持する。
    """
    if include_files is None:
        include_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    
    if exclude_files:
        include_files = [f for f in include_files if f not in exclude_files]

    records = []
    
    for file_name in include_files:
        file_path = os.path.join(DATA_DIR, file_name)
        if not os.path.exists(file_path):
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
                
        if isinstance(data, dict):
            data = [data]
            
        for row in data:
            if not isinstance(row, dict):
                continue
            
            date_str = row.get("date", "")
            facility = row.get("facility", "")
            weather = row.get("weather", "")
            water_temp = row.get("waterTemp", "")
            tide = row.get("tide", "")
            catches = row.get("catches", [])
            
            # 各魚種のカウントを初期化
            species_counts = {sp: 0 for sp in TARGET_SPECIES_LIST}
            
            for catch in catches:
                try:
                    c = int(catch.get("count") or 0)
                except (ValueError, TypeError):
                    c = 1 
                    
                catch_name = catch.get("name", "")
                
                # 指定した主要魚種が含まれているかチェック
                for sp in TARGET_SPECIES_LIST:
                    if sp in catch_name:
                        species_counts[sp] += c

            # 基本情報と魚種別カウントを結合
            record = {
                "date": date_str,
                "facility": facility,
                "weather": weather,
                "water_temp": water_temp,
                "tide": tide,
            }
            record.update(species_counts)
            records.append(record)

    df = pd.DataFrame(records)
    return df

def preprocess_data_b(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    特徴量エンジニアリングと前処理を行う（パターンB用）
    戻り値: (特徴量DataFrame X, 目的変数DataFrame Y)
    """
    if df.empty:
        raise ValueError("提供されたデータフレームが空です")

    # 日付から月を抽出
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['month'] = df['date'].dt.month
    df['day_of_week'] = df['date'].dt.dayofweek
    
    # 水温を数値化
    df['water_temp'] = pd.to_numeric(df['water_temp'], errors='coerce')
    df.fillna({'water_temp': df['water_temp'].mean()}, inplace=True)
    
    # カテゴリ変数の処理
    def simplify_weather(w):
        if pd.isna(w): return "不明"
        if "晴" in w: return "晴れ"
        if "雨" in w: return "雨"
        if "曇" in w: return "曇り"
        return "その他"
        
    df['weather_simple'] = df['weather'].apply(simplify_weather)
    
    features = ['month', 'day_of_week', 'water_temp', 'facility', 'weather_simple', 'tide']
    X = df[features]
    Y = df[TARGET_SPECIES_LIST] # 複数の目的変数
    
    # One-Hot Encoding
    X = pd.get_dummies(X, columns=['facility', 'weather_simple', 'tide'], drop_first=True)
    
    # 欠損値補完
    X.fillna(0, inplace=True)
    Y.fillna(0, inplace=True)
    
    return X, Y

if __name__ == "__main__":
    df_raw = load_data_b(include_files=["daikoku_2024_to_present.json"])
    print(f"ロード件数: {len(df_raw)}")
    if not df_raw.empty:
        X, Y = preprocess_data_b(df_raw)
        print("X shape:", X.shape)
        print("Y shape:", Y.shape)
        print("Y Categories:", Y.columns.tolist())
