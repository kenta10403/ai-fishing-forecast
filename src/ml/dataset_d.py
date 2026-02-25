import json
import os
import pandas as pd
from typing import List, Optional, Tuple

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

TARGET_SPECIES_LIST = [
    "アジ", "イワシ", "サバ", "スズキ", "シーバス", "クロダイ", "チヌ",
    "カサゴ", "メバル", "シロギス", "タコ", "イナダ", "ワラサ", "ブリ", "サワラ"
]

def load_trend_data(
    include_files: Optional[List[str]] = None,
    exclude_files: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    釣具屋データ（釣れた時だけ報告されるデータ）をロードし、
    日次・エリア別にグルーピングしてトレンド指数（報告人数や総釣果数）を算出する。
    """
    if include_files is None:
        # デフォルトでは釣具屋系と海釣り施設のデータ両方を対象とする
        include_files = [
            "casting_choka.json", 
            "johshuya_history.json",
            "honmoku_2024_to_present.json",
            "daikoku_2024_to_present.json",
            "isogo_2024_to_present.json",
            "ichihara_2024_to_present.json"
        ]
    
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
            # casting_chokaの {"metadata":..., "data":...} 構造対応
            if "data" in data and isinstance(data["data"], list):
                data = data["data"]
            else:
                data = [data]
            
        for row in data:
            if not isinstance(row, dict):
                continue
            
            # 関東圏の海釣りに限定する
            category = row.get("category", "")
            if category != "sea":
                continue
                
            area = row.get("area", "不明")
            if area not in ["東京都", "神奈川県", "千葉県", "埼玉県", "茨城県", "栃木県", "群馬県"]:
                continue
            
            date_str = row.get("date", "")
            if not date_str:
                date_str = row.get("fishingDate", "") # 上州屋などの表記揺れ対応
                
            shop = row.get("shopName", row.get("shop", "不明"))
            area = row.get("area", "不明")
            weather = row.get("weather", "不明")
            water_temp = row.get("waterTemp", "")
            visitors = row.get("visitors", 0)
            facility_type = row.get("facility", "shop") # 'honmoku', 'johshuya' etc.
            
            # 海釣り施設か釣具屋かの判定
            is_facility = facility_type in ["honmoku", "daikoku", "isogo", "ichihara"]
            weight = 1.0 if is_facility else 0.3 # 施設のデータ（生存者バイアスが少ない）を重視
            
            # 水温の数値化
            try:
                temp_val = float(water_temp) if water_temp else None
            except (ValueError, TypeError):
                temp_val = None

            catches = row.get("catches", [])
            
            for catch in catches:
                catch_name = catch.get("name", "")
                try:
                    c = int(catch.get("count") or 0)
                except (ValueError, TypeError):
                    c = 1 
                if c <= 0:
                    c = 1
                    
                matched_sp = None
                for sp in TARGET_SPECIES_LIST:
                    if sp in catch_name:
                        matched_sp = sp
                        # シーバス→スズキ、チヌ→クロダイ 等の名寄せ
                        if matched_sp == "シーバス": matched_sp = "スズキ"
                        if matched_sp == "チヌ": matched_sp = "クロダイ"
                        if matched_sp in ["ワラサ", "ブリ"]: matched_sp = "イナダ"
                        break
                
                if matched_sp:
                    records.append({
                        "date": date_str,
                        "shop": shop,
                        "area": area,
                        "weather": weather,
                        "water_temp": temp_val,
                        "visitors": visitors,
                        "is_facility": is_facility,
                        "weight": weight,
                        "species": matched_sp,
                        "counts": c,
                        "report": 1 # 1件の報告としてカウント
                    })

    df = pd.DataFrame(records)
    if df.empty:
        return df
        
    # 日付 × エリア × 魚種 ごとに集計 (グルーピング)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    grouped = df.groupby(['date', 'area', 'weather', 'species', 'is_facility', 'weight']).agg({
        'report': 'sum',
        'counts': 'sum',
        'visitors': 'max', # 1日の入場者数
        'water_temp': 'mean'
    }).reset_index()
    
    # トレンド指標の算出
    # 施設の場合: CPUE (Catch Per Unit Effort) = 釣果数 / 入場者数
    # 釣具屋の場合: 報告数ベースのスコア
    def calc_trend_score(row):
        if row['is_facility'] and row['visitors'] > 0:
            # 施設は「その日の1人あたりの平均釣果」をベースにする
            return (row['counts'] / row['visitors']) * 100 * row['weight']
        else:
            # 釣具屋は「報告の盛り上がり」をベースにする
            return (row['report'] * 10 + row['counts']) * row['weight']

    grouped['trend_score'] = grouped.apply(calc_trend_score, axis=1)
    
    return grouped

def preprocess_trend_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
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
