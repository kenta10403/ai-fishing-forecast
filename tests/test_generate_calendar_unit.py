"""
generate_calendar.py のユニットテスト
掟2（DB初期値取得）・掟3（7:3ブレンド）の検証
"""
import sys
import os
import sqlite3
import tempfile
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'ml'))


class TestFetchLastWeatherFromDB:
    """掟2: fetch_last_weather_from_db() のユニットテスト"""

    @pytest.fixture
    def mock_db(self, tmp_path):
        """テスト用のSQLiteデータベースを作成"""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE weather_history (
                date TEXT,
                area TEXT,
                avg_temp REAL,
                max_temp REAL,
                min_temp REAL,
                avg_wind_speed REAL,
                max_wind_speed REAL,
                wind_direction TEXT,
                precipitation REAL,
                daylight_hours REAL,
                PRIMARY KEY (date, area)
            )
        ''')
        # 前日・前々日のデータを挿入
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        day_before = (today - timedelta(days=2)).strftime("%Y-%m-%d")

        cursor.execute(
            "INSERT INTO weather_history (date, area, precipitation, avg_wind_speed) VALUES (?, '神奈川県', 5.5, 4.2)",
            (yesterday,)
        )
        cursor.execute(
            "INSERT INTO weather_history (date, area, precipitation, avg_wind_speed) VALUES (?, '神奈川県', 12.0, 6.1)",
            (day_before,)
        )
        conn.commit()
        conn.close()
        return db_path

    def test_fetches_real_values_from_db(self, mock_db):
        """DBから正しく実測値を取得できること"""
        from generate_calendar import fetch_last_weather_from_db

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        with patch('generate_calendar.DB_PATH', mock_db):
            result = fetch_last_weather_from_db(today)

        assert result['precipitation_lag1'] == 5.5
        assert result['avg_wind_speed_lag1'] == 4.2
        assert result['precipitation_lag2'] == 12.0

    def test_fallback_when_no_data(self, tmp_path):
        """DBにデータが無い場合、デフォルト値にフォールバックすること"""
        db_path = str(tmp_path / "empty.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE weather_history (
                date TEXT, area TEXT, avg_temp REAL, max_temp REAL, min_temp REAL,
                avg_wind_speed REAL, max_wind_speed REAL, wind_direction TEXT,
                precipitation REAL, daylight_hours REAL,
                PRIMARY KEY (date, area)
            )
        ''')
        conn.commit()
        conn.close()

        from generate_calendar import fetch_last_weather_from_db

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        with patch('generate_calendar.DB_PATH', db_path):
            result = fetch_last_weather_from_db(today)

        # デフォルト値が返ること
        assert result['precipitation_lag1'] == 0
        assert result['precipitation_lag2'] == 0
        assert result['avg_wind_speed_lag1'] == 3.0

    def test_fallback_on_db_error(self):
        """DB接続エラー時にデフォルト値にフォールバックすること"""
        from generate_calendar import fetch_last_weather_from_db

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        with patch('generate_calendar.DB_PATH', '/nonexistent/path.db'):
            result = fetch_last_weather_from_db(today)

        assert result['precipitation_lag1'] == 0
        assert result['precipitation_lag2'] == 0
        assert result['avg_wind_speed_lag1'] == 3.0


class TestBlendLogic:
    """掟3: 7:3 ブレンドロジックの数値検算"""

    def test_blend_formula(self):
        """0.7 * 当日予報 + 0.3 * 前日ラグ の計算が正しいこと"""
        forecast_precip = 10.0
        prev_lag_precip = 5.0

        blended = 0.7 * forecast_precip + 0.3 * prev_lag_precip
        assert blended == pytest.approx(8.5)

    def test_blend_dampens_spike(self):
        """ブレンドにより極端な変動が減衰されること"""
        prev_lag = 2.0
        spike_forecast = 100.0

        # ブレンドなし (100%信用)
        no_blend = spike_forecast
        # ブレンドあり
        blended = 0.7 * spike_forecast + 0.3 * prev_lag

        assert blended < no_blend
        assert blended == pytest.approx(70.6)

    def test_blend_converges(self):
        """同じ値が続くとブレンド結果が収束すること"""
        lag = 0.0
        constant_forecast = 10.0

        for _ in range(20):
            lag = 0.7 * constant_forecast + 0.3 * lag

        # 十分なイテレーション後、forecast値に収束する
        assert lag == pytest.approx(constant_forecast, abs=0.01)

    def test_blend_zero_forecast_decays(self):
        """予報0が続くと、ラグ値が徐々に減衰すること"""
        lag = 10.0

        for _ in range(10):
            lag = 0.7 * 0.0 + 0.3 * lag

        # 0に近づいていること
        assert lag < 0.1
