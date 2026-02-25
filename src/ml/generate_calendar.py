import os
import json
import joblib
import pandas as pd
import random
import urllib.request
from datetime import datetime, timedelta
import scipy.stats as stats

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_trend.pkl")

def get_tide_name(d):
    # Reference: 2026/02/17 is New Moon (Age 0) at 16:01
    # More accurate average lunar month is 29.53059
    ref = datetime(2026, 2, 17, 16, 1)
    diff = (d - ref).total_seconds() / (24 * 3600)
    age = diff % 29.53059
    
    # Standard Japanese Fishing Tide Classification (Approximate MIRC style)
    if age < 2.5 or (age >= 13.7 and age < 17.5) or age >= 28.2:
        return "大潮"
    if (age >= 2.5 and age < 5.5) or (age >= 10.5 and age < 13.7) or (age >= 17.5 and age < 20.5) or (age >= 25.5 and age < 28.2):
        return "中潮"
    if (age >= 5.5 and age < 8.5) or (age >= 20.5 and age < 23.5):
        return "小潮"
    if (age >= 8.5 and age < 9.5) or (age >= 23.5 and age < 24.5):
        return "長潮"
    if (age >= 9.5 and age < 10.5) or (age >= 24.5 and age < 25.5):
        return "若潮"
    return "中潮"

def fetch_weather(start_date, end_date, lat=35.44, lon=139.64):
    """
    Fetch weather from Open-Meteo API for Yokohama area.
    Combines Archive API (for past) and Forecast API (for future).
    """
    today = datetime.now()
    weather_map = {}

    def parse_wmo(code):
        if code == 0: return '晴れ'
        if code in [1, 2, 3, 45, 48]: return '曇り'
        return '雨' # 51+ (Drizzle, Rain, Snow, Thunderstorm) are all simplified as Rain

    # 1. Fetch Archive (Past up to yesterday)
    archive_end = min(end_date, today - timedelta(days=1))
    if start_date <= archive_end:
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_date.strftime('%Y-%m-%d')}&end_date={archive_end.strftime('%Y-%m-%d')}&daily=weather_code&timezone=Asia%2FTokyo"
        try:
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
                dates = data['daily']['time']
                codes = data['daily']['weather_code']
                for d, c in zip(dates, codes):
                    if c is not None:
                        weather_map[d] = parse_wmo(c)
        except Exception as e:
            print(f"Warning: Failed to fetch archive weather: {e}")

    # 2. Fetch Forecast (Today and future)
    forecast_start = max(start_date, today.replace(hour=0, minute=0, second=0, microsecond=0))
    if forecast_start <= end_date:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=weather_code&timezone=Asia%2FTokyo&past_days=0"
        try:
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
                dates = data['daily']['time']
                codes = data['daily']['weather_code']
                for d, c in zip(dates, codes):
                    if c is not None:
                        weather_map[d] = parse_wmo(c)
        except Exception as e:
            print(f"Warning: Failed to fetch forecast weather: {e}")

    return weather_map

def load_facility_weather():
    """
    Load historical weather records from facility JSON files to prioritize them for past dates.
    """
    proj_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    facility_files = [
        "honmoku_2024_to_present.json",
        "daikoku_2024_to_present.json",
        "isogo_2024_to_present.json",
        "ichihara_2024_to_present.json"
    ]
    
    facility_weather = {}
    for filename in facility_files:
        path = os.path.join(proj_root, "data", filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    
                    # Handle both structures: {"data": [...]} and raw [...]
                    if isinstance(content, dict):
                        data_list = content.get('data', [])
                    elif isinstance(content, list):
                        data_list = content
                    else:
                        data_list = []
                        
                    for item in data_list:
                        d = item.get('date', '')
                        w = item.get('weather', '')
                        if d and w:
                            # Use canonical ISO or YYYY-MM-DD for matching
                            date_key = d.replace('/', '-')
                            if w != '不明':
                                facility_weather[date_key] = w
            except Exception as e:
                print(f"Warning: Failed to load {filename}: {e}")
    return facility_weather

def generate_calendar_data(start_date, num_days=42, output_file="src/data/frontend_calendar.json"):
    if not os.path.exists(MODEL_PATH):
        print(f"Error: Model not found at {MODEL_PATH}")
        return

    model_data = joblib.load(MODEL_PATH)
    model = model_data["model"]
    feature_cols = model_data["features"]
    score_distribution = model_data.get("score_distribution", [])
    period_water_temps = model_data.get("period_water_temps", {})
    seasonal_potential = model_data.get("seasonal_potential", {})
    
    today = datetime.now()
    end_date = start_date + timedelta(days=num_days - 1)
    
    api_weather = fetch_weather(start_date, end_date)
    facility_weather = load_facility_weather()
    
    days = []
    
    # Target Kanto area and popular species for general calendar
    target_area = "神奈川県"
    target_species = "アジ"
    
    for i in range(num_days):
        d = start_date + timedelta(days=i)
        date_iso = d.strftime('%Y-%m-%d')
        
        # Determine day type
        if d.date() < today.date():
            day_type = 'past'
        elif d.date() <= (today + timedelta(days=7)).date():
            day_type = 'forecast'
        else:
            day_type = 'base'
            
        # Get real weather or fallback
        # 1. Check facility records (Priority for past)
        # 2. Check API (For future or missing facility data)
        # 3. Fallback to sunny
        weather_simple = facility_weather.get(date_iso, api_weather.get(date_iso, '晴れ'))
        
        month = d.month
        day_num = d.day
        part = 0 if day_num <= 10 else 1 if day_num <= 20 else 2
        period_of_year = (month - 1) * 3 + part + 1
        
        # 水温の設定（予測時はその時期の平均、実績時はデータから取るのが理想だが一旦平均）
        water_temp = float(period_water_temps.get(str(period_of_year), 15.0))
        
        input_row = {
            "period_of_year": [period_of_year],
            "day_of_week": [d.weekday()],
            "area": [target_area],
            "weather_simple": [weather_simple],
            "species": [target_species],
            "water_temp": [water_temp]
        }
        
        df_input = pd.DataFrame(input_row)
        X = pd.get_dummies(df_input, columns=['area', 'weather_simple', 'species'])
        X = X.reindex(columns=feature_cols, fill_value=0)
        
        # Predict trend score
        raw_score = float(model.predict(X)[0])
        
        # 1. データ駆動型のシーズナリティ補正（36期別）
        # 学習データから抽出した「その時期（上・中・下旬）の平均的なポテンシャル」を適用
        period_key = str(period_of_year)
        potential_factor = float(seasonal_potential.get(period_key, 0.7))
        
        # 水温による微調整 (15度を基準に、低いとさらに下がり、高いと活性が上がる)
        # 1度につき5%変動させる
        temp_factor = 1.0 + (water_temp - 15.0) * 0.05
        temp_factor = max(0.6, min(1.2, temp_factor))
        
        final_seasonal_factor = potential_factor * temp_factor

        if len(score_distribution) > 0:
            # その「条件（潮・天気等）」における相対的な強さ（0-100）
            pct_score = stats.percentileofscore(score_distribution, raw_score, kind='weak')
            # シーズン全体のポテンシャルを掛け合わせることで、絶対評価に変換
            score = int(pct_score * final_seasonal_factor)
        else:
            score = 50
            
        score = max(5, min(100, score))
        tide = get_tide_name(d)
        
        trend = 'fire' if score >= 80 else 'hot' if score >= 60 else 'bad' if score < 40 else 'normal'
        
        details = (
            f"AIの分析によると、{target_area}では{target_species}の活性が非常に高まっています。" if score > 70 else
            f"{target_area}の{target_species}は平年並みの推移です。潮回りを意識した釣行をおすすめします。"
        )
        if day_type == 'base':
            details = "天気予報データがないため、例年の傾向と潮回りのみで算出した期待値です。"

        days.append({
            "date": d.strftime("%Y/%m/%d"),
            "type": day_type,
            "score": score,
            "weather": 'sunny' if weather_simple == '晴れ' else 'rain' if weather_simple == '雨' else 'cloudy',
            "tide": tide,
            "trend": trend,
            "details": details
        })
        
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(days, f, ensure_ascii=False, indent=2)
        
    print(f"Generated {len(days)} calendar days to {output_file} (Real Data Model)")

if __name__ == "__main__":
    # Start from Jan 1st 2025 for historical comparison
    start = datetime(2025, 1, 1)
    
    # Path for frontend data
    proj_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    output = os.path.join(proj_root, "src/data/frontend_calendar.json")
    
    # Generate around 1.5 years of data (from Jan 2025 to May 2026)
    # 365 (2025) + 150 (2026) = 515 days
    generate_calendar_data(start, 515, output)
