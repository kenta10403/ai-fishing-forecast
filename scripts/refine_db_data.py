import sqlite3
import re

DB_PATH = 'data/fishing_forecast.db'

def zen_to_han(text):
    if not text: return text
    return text.translate(str.maketrans(
        '０１２３４５６７８９',
        '0123456789'
    ))

def normalize_weather(w):
    if not w: return w
    w = w.replace('くもり', '曇り').replace('はれ', '晴れ').replace('あめ', '雨')
    w = w.replace('曇', '曇り').replace('曇りり', '曇り') # 重複修正向け
    
    # "BのちA", "B後A" -> A
    if 'のち' in w:
        w = w.split('のち')[-1]
    if '後' in w:
        w = w.split('後')[-1]
    
    # "A時々B", "A一時B" -> A
    if '時々' in w:
        w = w.split('時々')[0]
    if '一時' in w:
        w = w.split('一時')[0]
        
    return w.strip().replace('曇りり', '曇り') # 念押し

def extract_count_from_size(size):
    if not size: return None
    size = zen_to_han(size)
    
    # "15 - 32 匹" とか "合計 40 匹" から数字を抽出
    # 複数箇所に数字がある場合（"15-32匹"）、最後の数値を合計とみなすか？
    # ユーザー指示は「◯匹をcountに移植」なので、"NN匹" の直前の数字を取るのが安全
    matches = re.findall(r'(\d+)\s*匹', size)
    if matches:
        # 範囲指定（15-32匹）の場合は、とりあえず大きい方（後の方）を取る
        return int(matches[-1])
    return None

def refine_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Normalizing weather in facility_logs...")
    cursor.execute("SELECT id, weather FROM facility_logs")
    for row_id, weather in cursor.fetchall():
        new_w = normalize_weather(weather)
        if new_w != weather:
            cursor.execute("UPDATE facility_logs SET weather = ? WHERE id = ?", (new_w, row_id))
            
    print("Normalizing weather in shop_logs...")
    cursor.execute("SELECT id, weather FROM shop_logs")
    for row_id, weather in cursor.fetchall():
        new_w = normalize_weather(weather)
        if new_w != weather:
            cursor.execute("UPDATE shop_logs SET weather = ? WHERE id = ?", (new_w, row_id))
            
    print("Extracting counts from size in shop_catches...")
    # countが空(0かNULL)のものだけ対象にする
    cursor.execute("SELECT id, size, count FROM shop_catches WHERE count IS NULL OR count = 0")
    updates = 0
    for row_id, size, current_count in cursor.fetchall():
        extracted = extract_count_from_size(size)
        if extracted is not None:
            cursor.execute("UPDATE shop_catches SET count = ? WHERE id = ?", (extracted, row_id))
            updates += 1
            
    conn.commit()
    conn.close()
    print(f"Refinement complete. Extracted {updates} counts from size strings.")

if __name__ == "__main__":
    refine_data()
