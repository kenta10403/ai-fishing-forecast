import sqlite3
import pandas as pd
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "../../data/fishing_forecast.db")

def analyze_monthly_trends():
    conn = sqlite3.connect(DB_PATH)
    
    print("📋 月別データ・ソース別比較分析（全期間）")
    
    # 日付形式が YYYY/MM/DD なので substr で月を抽出
    # 1. 釣具屋データ
    shop_query = """
    SELECT 
        substr(sl.date, 6, 2) as month,
        sc.species,
        SUM(sc.count) as total_count
    FROM shop_catches sc
    JOIN shop_logs sl ON sc.log_id = sl.id
    WHERE sc.species NOT IN ('ワカサギ', 'ニジマス', 'ヘラブナ', 'アユ', 'トラウト', 'レインボートラウト', 'ヤマメ', 'イワナ')
    GROUP BY month, sc.species
    """
    df_shop = pd.read_sql_query(shop_query, conn)
    df_shop['source'] = 'Shop'
    
    # 2. 釣り施設データ
    facility_query = """
    SELECT 
        substr(fl.date, 6, 2) as month,
        fc.species,
        SUM(fc.count) as total_count
    FROM facility_catches fc
    JOIN facility_logs fl ON fc.log_id = fl.id
    GROUP BY month, fc.species
    """
    df_facility = pd.read_sql_query(facility_query, conn)
    df_facility['source'] = 'Facility'
    
    # 全データの結合
    df_all = pd.concat([df_shop, df_facility])
    df_all = df_all.dropna(subset=['month'])
    # "/" などの余計な文字が入る可能性を排除
    df_all['month'] = df_all['month'].str.replace('/', '').astype(int)
    
    # --- A. 全魚種合計の月別推移 ---
    monthly_all = df_all.groupby(['month', 'source'])['total_count'].sum().unstack()
    
    print("\n📊 【全魚種合計】ソース別 月別釣果数")
    print("-" * 60)
    print(monthly_all)
    
    # --- B. 主要魚種別の月別推移 ---
    major_species = ['アジ', 'シーバス', 'クロダイ', 'メバル', 'カサゴ', 'タチウオ', 'カワハギ', 'キス', 'イナダ', 'アオリイカ']
    
    print("\n📊 【主要魚種別】ソース別 月別釣果数")
    for species in major_species:
        species_data = df_all[df_all['species'].str.contains(species, na=False)]
        if species_data.empty:
            continue
        
        print(f"\n--- {species} ---")
        species_monthly = species_data.groupby(['month', 'source'])['total_count'].sum().unstack()
        species_monthly = species_monthly.reindex(range(1, 13)).fillna(0).astype(int)
        print(species_monthly)

    conn.close()

if __name__ == "__main__":
    analyze_monthly_trends()
