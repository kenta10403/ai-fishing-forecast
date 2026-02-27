"""
データ分布を確認するデバッグスクリプト
DO、COD、波高の異常を調査する
"""
import pandas as pd
import numpy as np
from dataset_real_marine import create_dataset

print("🔍 データ分布調査開始...")
df = create_dataset()

# 問題のある特徴量を調査
problem_cols = ['real_do', 'real_cod', 'real_wave_height', 'real_water_temp', 'real_salinity']

print("\n" + "="*60)
print("📊 基本統計量")
print("="*60)
for col in problem_cols:
    print(f"\n【{col}】")
    print(df[col].describe())
    print(f"  欠損値数: {df[col].isnull().sum()}")
    print(f"  ユニーク値数: {df[col].nunique()}")
    print(f"  分散: {df[col].var():.6f}")
    print(f"  標準偏差: {df[col].std():.6f}")

    # 異常値チェック（3σ外）
    mean = df[col].mean()
    std = df[col].std()
    outliers = df[(df[col] < mean - 3*std) | (df[col] > mean + 3*std)]
    print(f"  異常値（3σ外）の数: {len(outliers)}")

    # 最頻値
    print(f"  最頻値: {df[col].mode().values if len(df[col].mode()) > 0 else 'なし'}")

print("\n" + "="*60)
print("📈 DO、COD、波高の実測データ数")
print("="*60)

# 元のDBデータを確認
import sqlite3
import os
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'fishing_forecast.db')
conn = sqlite3.connect(DB_PATH)

# DO、COD（千葉県水質データ）
print("\n【千葉県水質データ】")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*), COUNT(DISTINCT date), MIN(date), MAX(date) FROM tokyo_bay_marine_data")
result = cursor.fetchone()
print(f"  総レコード数: {result[0]}")
print(f"  ユニーク日付数: {result[1]}")
print(f"  期間: {result[2]} 〜 {result[3]}")

cursor.execute("SELECT do_level, cod FROM tokyo_bay_marine_data WHERE do_level IS NOT NULL OR cod IS NOT NULL LIMIT 20")
sample = cursor.fetchall()
print(f"\n  サンプルデータ（先頭20件）:")
for row in sample[:10]:
    print(f"    DO={row[0]}, COD={row[1]}")

# 波高データ
print("\n【波高データ (marine_forecast_history)】")
cursor.execute("SELECT COUNT(*), COUNT(DISTINCT date), MIN(date), MAX(date) FROM marine_forecast_history")
result = cursor.fetchone()
print(f"  総レコード数: {result[0]}")
print(f"  ユニーク日付数: {result[1]}")
print(f"  期間: {result[2]} 〜 {result[3]}")

cursor.execute("SELECT date, wave_height_max FROM marine_forecast_history WHERE wave_height_max IS NOT NULL LIMIT 10")
sample = cursor.fetchall()
print(f"\n  サンプルデータ（先頭10件）:")
for row in sample:
    print(f"    {row[0]}: 波高={row[1]}")

conn.close()

print("\n" + "="*60)
print("🔍 補間後のデータの連続性チェック")
print("="*60)

# DO、CODの値が連続的すぎるか確認（線形補間の影響）
for col in ['real_do', 'real_cod']:
    print(f"\n【{col}】先頭30日間:")
    print(df[col].head(30).values)

    # 差分を確認（線形補間だと差分が一定）
    diff = df[col].diff().dropna()
    print(f"  差分の標準偏差: {diff.std():.6f}")
    print(f"  差分の最頻値: {diff.mode().values if len(diff.mode()) > 0 else 'なし'}")

print("\n✅ 調査完了！")
