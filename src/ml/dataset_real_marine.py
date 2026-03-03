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

    # 1. 釣果データの取得 (目的変数用) - 施設データのみ使用
    # 改善 #2: 店舗(shop)データとの混合を廃止。施設データのCPUEのみを正確に計算する。
    print("  📊 釣果データを読み込み中 (施設データのみ)...")
    catches_query = """
    SELECT fl.date,
           SUM(COALESCE(fc.count, 1)) * 1.0 / fl.visitors as catch_count
    FROM facility_catches fc
    JOIN facility_logs fl ON fc.log_id = fl.id
    WHERE fl.visitors > 0
    GROUP BY fl.date, fl.facility
    """
    df_catches = fetch_data(catches_query, conn)
    # 同日に複数施設のデータがある場合は、日付ごとに平均CPUEを算出
    df_catches = df_catches.groupby(df_catches.index).mean()

    # 2. 気象データの取得 (特徴量: 神奈川県) - これをベースのDataFrameにする
    # 海況モデルは全期間の気象データで学習するため、気象データをベースにする。
    print("  ☀️ 気象データを読み込み中...")
    weather_query = """
    SELECT date, avg_temp, max_temp, min_temp, avg_wind_speed, max_wind_speed, precipitation, daylight_hours
    FROM weather_history
    WHERE area = '神奈川県'
    """
    df = fetch_data(weather_query, conn)
    
    # 釣果データをマージ (改善 #3: 報告なし日はNaNのまま残す。fillna(0)にしない)
    df = df.merge(df_catches, left_index=True, right_index=True, how='left')


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

    # 5. 波浪・河川流量データ (目的変数/特徴量)
    print("  🌊 波浪・河川流量データを読み込み中...")
    marine_forecast_query = """
    SELECT date, wave_height_max as real_wave_height, wave_direction_dominant, river_discharge as real_river_discharge
    FROM marine_forecast_history
    """
    df_marine_forecast = fetch_data(marine_forecast_query, conn)
    df = df.merge(df_marine_forecast, left_index=True, right_index=True, how='left')

    # 6. 前処理 (Data Leakage を防ぐため、ここでは一括補完を行わない)
    print("  🧪 欠損値はそのままにする (学習時に分割後補完を行う)")
    
    # 最小限の埋め (潮汐など、不連続で過去から引き継げるもののみ)
    df['tide_level'] = df['tide_level'].ffill().fillna(2)
    
    # 波浪・河川トラッキングデータ：NULLはそのまま（モデル学習時に除外）
    # 注: 以前は ffill/bfill で補完していたが、偽データで学習する問題があったため廃止
    df['wave_direction_dominant'] = df['wave_direction_dominant'].fillna(180)  # 方向のみデフォルト値

    # 海界ターゲット列
    marine_cols = ['real_water_temp', 'real_salinity', 'real_do', 'real_cod', 'real_transparency', 'wave_direction_dominant']

    # 7. 追加特徴量エンジニアリング (前日値など)
    # 未来の情報が漏れないよう、shift(1) のみを使ってラグを作成する
    df['precipitation_lag1'] = df['precipitation'].shift(1).fillna(0)
    df['precipitation_lag2'] = df['precipitation'].shift(2).fillna(0)
    df['avg_wind_speed_lag1'] = df['avg_wind_speed'].shift(1).fillna(0)
    
    # 前日の各種海況 (bfill()など未来を参照する補完は避ける)
    # 注: NULLはそのまま。モデル学習時に分割後補正される
    for col in marine_cols + ['real_wave_height', 'real_river_discharge']:
        df[f'{col}_lag1'] = df[col].shift(1) # ここではまだNaNが残る
        
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
