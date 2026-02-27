import sqlite3
import pandas as pd
import numpy as np
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__abspath__)), 'data', 'fishing_forecast.db') if '__abspath__' in globals() else 'data/fishing_forecast.db'

def fetch_data(query, conn):
    """DBからデータを取得し、dateをdatetime型にしてインデックスにする"""
    df = pd.read_sql_query(query, conn)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    return df

def create_dataset():
    """
    全実測データを結合し、AI学習用の完全なデータセットを作成する
    """
    print("🌊 実測データ結合プロセス開始...")
    conn = sqlite3.connect(DB_PATH)

    # 1. 釣果データの取得 (目的変数用)
    print("  📊 釣果データを読み込み中...")
    catches_query = """
    SELECT date, SUM(COALESCE(count, 1)) * 1.0 / COUNT(DISTINCT log_id) as catch_count
    FROM (
        SELECT sl.date, sc.count, sc.log_id FROM shop_catches sc
        JOIN shop_logs sl ON sc.log_id = sl.id
        WHERE sl.category = 'sea'
        AND sl.area IN ('東京都', '神奈川県', '千葉県')
        UNION ALL
        SELECT fl.date, fc.count, fc.log_id FROM facility_catches fc
        JOIN facility_logs fl ON fc.log_id = fl.id
    )
    GROUP BY date
    """
    df_catches = fetch_data(catches_query, conn)
    
    # 全日付のベースとなるカレンダーを作成 (2009-01-01 から 2024-12-31)
    base_dates = pd.date_range(start='2009-01-01', end='2024-12-31', freq='D')
    df_base = pd.DataFrame(index=base_dates)
    
    # 釣果データをマージ (釣果がない日は0)
    df = df_base.merge(df_catches, left_index=True, right_index=True, how='left')
    df['catch_count'] = df['catch_count'].fillna(0)

    # 2. 気象データの取得 (特徴量: 東京)
    print("  ☀️ 気象データを読み込み中...")
    weather_query = """
    SELECT date, avg_temp, max_temp, min_temp, avg_wind_speed, max_wind_speed, precipitation, daylight_hours
    FROM weather_history
    WHERE area = '神奈川県'
    """
    df_weather = fetch_data(weather_query, conn)
    df = df.merge(df_weather, left_index=True, right_index=True, how='left')

    # 3. 潮汐データの取得 (特徴量: 東京)
    print("  🌙 潮汐データを読み込み中...")
    tide_query = """
    SELECT date, tide
    FROM tide_history
    """
    df_tide = fetch_data(tide_query, conn)
    
    # 潮回りをカテゴリ変数(数値)に変換
    tide_mapping = {'大潮': 4, '中潮': 3, '小潮': 2, '長潮': 1, '若潮': 0}
    df_tide['tide_level'] = df_tide['tide'].map(tide_mapping).fillna(2) # 不明は小潮扱い
    df_tide = df_tide.drop(columns=['tide'])
    
    df = df.merge(df_tide, left_index=True, right_index=True, how='left')

    # 4. 千葉県 実測水質データ (目的変数/特徴量)
    # 日付ごとに複数地点のデータがあるため、平均または中央値をとって代表値にする
    print("  💧 千葉県水質データを読み込み中...")
    chiba_query = """
    SELECT date, water_temp as real_water_temp, salinity as real_salinity, 
           do_level as real_do, cod as real_cod, transparency as real_transparency
    FROM tokyo_bay_marine_data
    """
    df_chiba_raw = fetch_data(chiba_query, conn)
    # 日付ごとに集約 (平均値)
    df_chiba = df_chiba_raw.groupby('date').mean()
    df = df.merge(df_chiba, left_index=True, right_index=True, how='left')
    
    # 黒潮大蛇行フラグ (2017/8/1 〜 2025/4/1)
    df['is_kuroshio_meander'] = 0
    meander_mask = (df.index >= '2017-08-01') & (df.index <= '2025-04-30')
    df.loc[meander_mask, 'is_kuroshio_meander'] = 1

    # 5. Open-Meteo 波浪・河川流量データ (目的変数/特徴量)
    print("  🌊 波浪・河川流量データを読み込み中...")
    openmeteo_query = """
    SELECT date, wave_height_max as real_wave_height, wave_direction_dominant, river_discharge as real_river_discharge
    FROM openmeteo_marine_history
    """
    df_openmeteo = fetch_data(openmeteo_query, conn)
    df = df.merge(df_openmeteo, left_index=True, right_index=True, how='left')

    # 6. 前処理と欠損値補完 (最重要)
    print("  🔧 欠損値の補完処理を実行中...")
    
    # 天気関連の欠損値補完 (基本的にあるはずだが念のため)
    weather_cols = ['avg_temp', 'max_temp', 'min_temp', 'avg_wind_speed', 'max_wind_speed', 'precipitation', 'daylight_hours']
    for col in weather_cols:
         df[col] = df[col].ffill().bfill().fillna(0)
    
    df['tide_level'] = df['tide_level'].ffill().bfill().fillna(2)
    
    # 波浪・河川トラッキングデータ：NULLはそのまま（モデル学習時に除外）
    # 注: 以前は ffill/bfill で補完していたが、偽データで学習する問題があったため廃止
    df['wave_direction_dominant'] = df['wave_direction_dominant'].fillna(180)  # 方向のみデフォルト値

    # 千葉県水質データ：NULLはそのまま（モデル学習時に除外）
    # 注: 以前は線形補間していたが、実測値が少ないためモデル精度が崩壊していた
    # 実測データのみで学習する方針に変更
    marine_cols = ['real_water_temp', 'real_salinity', 'real_do', 'real_cod', 'real_transparency']
    # 補間は一切行わない！

    # 7. 追加特徴量エンジニアリング (前日値など)
    # 河川流量は前日に降った雨の影響を強く受けるため、前日の雨量などをモデルに教える
    df['precipitation_lag1'] = df['precipitation'].shift(1).fillna(0)
    df['precipitation_lag2'] = df['precipitation'].shift(2).fillna(0)
    df['avg_wind_speed_lag1'] = df['avg_wind_speed'].shift(1).fillna(0)
    
    # 前日の各種海況(自己回帰的な情報)
    # 注: NULLはそのまま。モデル学習時に除外される
    for col in marine_cols + ['real_wave_height', 'real_river_discharge']:
        df[f'{col}_lag1'] = df[col].shift(1)  # 補間なし
        
    df['month'] = df.index.month
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
    df['day_of_week'] = df.index.dayofweek
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)

    print(f"✅ データセット作成完了: {df.shape[0]}行 × {df.shape[1]}列")
    conn.close()
    return df

if __name__ == "__main__":
    df = create_dataset()
    print("\n--- 結合データ サンプル ---")
    print(df.tail())
