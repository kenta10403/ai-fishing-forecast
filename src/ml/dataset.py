import json
import os
import pandas as pd
from typing import List, Optional, Tuple

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

def load_data(
    include_files: Optional[List[str]] = None,
    exclude_files: Optional[List[str]] = None,
    target_species: Optional[str] = None
) -> pd.DataFrame:
    """
    指定されたJSONファイル群をロードし、DataFrameに変換して返す。
    target_speciesが指定された場合、その魚種の釣果数を目的変数として抽出。
    指定がない場合は、全魚種の総釣果数を大漁スコアとして抽出。
    """
    if include_files is None:
        include_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    
    if exclude_files:
        include_files = [f for f in include_files if f not in exclude_files]

    records = []
    
    for file_name in include_files:
        file_path = os.path.join(DATA_DIR, file_name)
        if not os.path.exists(file_path):
            print(f"警告: {file_path} が見つかりませんでした。スキップします。")
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"警告: {file_name} は不正なJSONです。スキップします。")
                continue
                
        # dataが単一の辞書の場合はリスト化
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
            
            # 釣果数の集計
            total_count = 0
            target_count = 0
            
            for catch in catches:
                try:
                    c = int(catch.get("count") or 0)
                except (ValueError, TypeError):
                    c = 1 # countがパースできない(文字列やnull)場合は最低1を保証するなど適宜
                    
                total_count += c
                
                if target_species and target_species in catch.get("name", ""):
                    target_count += c

            # 学習のターゲット値
            target_value = target_count if target_species else total_count
            
            records.append({
                "date": date_str,
                "facility": facility,
                "weather": weather,
                "water_temp": water_temp,
                "tide": tide,
                "target_score": target_value
            })

    df = pd.DataFrame(records)
    return df

def preprocess_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """
    特徴量エンジニアリングと前処理を行う
    """
    if df.empty:
        raise ValueError("提供されたデータフレームが空です")

    # 日付から月を抽出
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['month'] = df['date'].dt.month
    df['day_of_week'] = df['date'].dt.dayofweek
    
    # 水温を数値化
    df['water_temp'] = pd.to_numeric(df['water_temp'], errors='coerce')
    df['water_temp'].fillna(df['water_temp'].mean(), inplace=True)
    
    # カテゴリ変数の処理（One-Hot Encodingなど）
    # 天気を簡易なカテゴリに
    def simplify_weather(w):
        if pd.isna(w): return "不明"
        if "晴" in w: return "晴れ"
        if "雨" in w: return "雨"
        if "曇" in w: return "曇り"
        return "その他"
        
    df['weather_simple'] = df['weather'].apply(simplify_weather)
    
    features = ['month', 'day_of_week', 'water_temp', 'facility', 'weather_simple', 'tide']
    X = df[features]
    y = df['target_score']
    
    # One-Hot Encoding
    X = pd.get_dummies(X, columns=['facility', 'weather_simple', 'tide'], drop_first=True)
    
    # 欠損値補完
    X.fillna(0, inplace=True)
    
    return X, y

if __name__ == "__main__":
    # テスト
    df_raw = load_data(include_files=["daikoku_2024_to_present.json"])
    print(f"ロード件数: {len(df_raw)}")
    if not df_raw.empty:
        X, y = preprocess_data(df_raw)
        print("X shape:", X.shape)
        print("y shape:", y.shape)
        print(X.head(3))
