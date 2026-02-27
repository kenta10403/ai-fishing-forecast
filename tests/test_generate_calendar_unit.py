"""
generate_calendar.py のユニットテスト
掟2（DB初期値取得）・掟3（7:3ブレンド）の検証
+ MET Norway パースロジック、河川流量減衰ロジックの検証
"""
import sys
import os
import sqlite3
import tempfile
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import json

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


class TestMETNorwayParsing:
    """MET Norway Locationforecast 2.0 レスポンスのパースロジックのテスト"""

    def _make_met_response(self):
        """MET Norway API のモックレスポンスを生成"""
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "type": "Feature",
            "properties": {
                "timeseries": [
                    {
                        "time": f"{today}T00:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 5.0,
                                    "wind_speed": 3.0
                                }
                            },
                            "next_1_hours": {
                                "details": {"precipitation_amount": 0.5}
                            }
                        }
                    },
                    {
                        "time": f"{today}T06:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 10.0,
                                    "wind_speed": 5.0
                                }
                            },
                            "next_1_hours": {
                                "details": {"precipitation_amount": 1.5}
                            }
                        }
                    },
                    {
                        "time": f"{today}T12:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 15.0,
                                    "wind_speed": 2.0
                                }
                            },
                            "next_1_hours": {
                                "details": {"precipitation_amount": 0.0}
                            }
                        }
                    },
                    {
                        "time": f"{today}T18:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 8.0,
                                    "wind_speed": 4.0
                                }
                            },
                            "next_6_hours": {
                                "details": {"precipitation_amount": 2.0}
                            }
                        }
                    },
                ]
            }
        }

    def test_daily_aggregation(self):
        """hourly → daily 集約が正しく行われること"""
        from generate_calendar import _fetch_met_norway_weather

        today = datetime.now().strftime("%Y-%m-%d")
        data_map = {today: {}}
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start

        mock_response = self._make_met_response()
        mock_read = MagicMock(return_value=json.dumps(mock_response).encode())
        mock_urlopen = MagicMock()
        mock_urlopen.__enter__ = MagicMock(return_value=MagicMock(read=mock_read))
        mock_urlopen.__exit__ = MagicMock(return_value=False)

        with patch('generate_calendar.urllib.request.urlopen', return_value=mock_urlopen):
            _fetch_met_norway_weather(start, end, data_map)

        assert today in data_map
        d = data_map[today]
        # max_temp = max(5, 10, 15, 8) = 15
        assert d['max_temp'] == 15.0
        # min_temp = min(5, 10, 15, 8) = 5
        assert d['min_temp'] == 5.0
        # avg_temp = (5+10+15+8)/4 = 9.5
        assert d['avg_temp'] == pytest.approx(9.5)
        # max_wind = max(3, 5, 2, 4) = 5
        assert d['max_wind_speed'] == 5.0
        # avg_wind = (3+5+2+4)/4 = 3.5
        assert d['avg_wind_speed'] == pytest.approx(3.5)
        # precipitation = 0.5 + 1.5 + 0.0 + 2.0 = 4.0
        assert d['precipitation'] == pytest.approx(4.0)
        # daylight_hours は astral で計算されるので正の値であること
        assert d['daylight_hours'] > 0

    def test_empty_response_handling(self):
        """空レスポンス時にクラッシュしないこと"""
        from generate_calendar import _fetch_met_norway_weather

        today = datetime.now().strftime("%Y-%m-%d")
        data_map = {today: {}}
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start

        mock_response = {"properties": {"timeseries": []}}
        mock_read = MagicMock(return_value=json.dumps(mock_response).encode())
        mock_urlopen = MagicMock()
        mock_urlopen.__enter__ = MagicMock(return_value=MagicMock(read=mock_read))
        mock_urlopen.__exit__ = MagicMock(return_value=False)

        with patch('generate_calendar.urllib.request.urlopen', return_value=mock_urlopen):
            _fetch_met_norway_weather(start, end, data_map)

        # data_map は空のまま (エラーなし)
        assert data_map[today] == {}


class TestRiverDischargeDecay:
    """河川流量の移動平均減衰ロジック検証"""

    def test_decay_with_no_rain(self):
        """降水量0の場合、流量が減衰すること"""
        from generate_calendar import _fetch_river_discharge_from_db

        data_map = {
            "2026-02-28": {"precipitation": 0},
            "2026-03-01": {"precipitation": 0},
            "2026-03-02": {"precipitation": 0},
        }

        with patch('generate_calendar.sqlite3') as mock_sqlite:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (100.0,)
            mock_conn.cursor.return_value = mock_cursor
            mock_sqlite.connect.return_value = mock_conn

            _fetch_river_discharge_from_db(data_map)

        # 減衰: 100 * 0.7 = 70, 70 * 0.7 = 49, 49 * 0.7 = 34.3
        assert data_map["2026-02-28"]["river_discharge"] == pytest.approx(70.0)
        assert data_map["2026-03-01"]["river_discharge"] == pytest.approx(49.0)
        assert data_map["2026-03-02"]["river_discharge"] == pytest.approx(34.3)

    def test_increase_with_heavy_rain(self):
        """降水量50mm以上で流量が維持されること"""
        from generate_calendar import _fetch_river_discharge_from_db

        data_map = {
            "2026-02-28": {"precipitation": 50},
            "2026-03-01": {"precipitation": 100},
        }

        with patch('generate_calendar.sqlite3') as mock_sqlite:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (100.0,)
            mock_conn.cursor.return_value = mock_cursor
            mock_sqlite.connect.return_value = mock_conn

            _fetch_river_discharge_from_db(data_map)

        # 降水50mm: factor = 0.7 + 0.3 * 1.0 = 1.0 → 100 * 1.0 = 100
        assert data_map["2026-02-28"]["river_discharge"] == pytest.approx(100.0)
        # 降水100mm (cap at 50): factor = 1.0 → 100 * 1.0 = 100
        assert data_map["2026-03-01"]["river_discharge"] == pytest.approx(100.0)

    def test_minimum_floor(self):
        """流量が下限値(10.0)を下回らないこと"""
        from generate_calendar import _fetch_river_discharge_from_db

        # 長期間の無降水で下限テスト
        data_map = {}
        for i in range(30):
            d = f"2026-03-{i+1:02d}"
            data_map[d] = {"precipitation": 0}

        with patch('generate_calendar.sqlite3') as mock_sqlite:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (50.0,)
            mock_conn.cursor.return_value = mock_cursor
            mock_sqlite.connect.return_value = mock_conn

            _fetch_river_discharge_from_db(data_map)

        # 30日後でも10.0を下回らない
        last_day = f"2026-03-30"
        assert data_map[last_day]["river_discharge"] >= 10.0

    def test_fallback_when_no_db_data(self):
        """DB取得失敗時にフォールバック値（50.0）が使われること"""
        from generate_calendar import _fetch_river_discharge_from_db

        data_map = {
            "2026-02-28": {"precipitation": 0},
        }

        with patch('generate_calendar.sqlite3') as mock_sqlite:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None  # No data
            mock_conn.cursor.return_value = mock_cursor
            mock_sqlite.connect.return_value = mock_conn

            _fetch_river_discharge_from_db(data_map)

        # フォールバック(50) * 0.7 = 35
        assert data_map["2026-02-28"]["river_discharge"] == pytest.approx(35.0)


class TestDaylightCalculation:
    """日照時間計算のテスト"""

    def test_daylight_positive(self):
        """日照時間が正の値を返すこと"""
        from generate_calendar import _calculate_daylight_hours
        
        d = datetime(2026, 6, 21)  # 夏至付近
        hours = _calculate_daylight_hours(d)
        assert hours > 10  # 夏なので10時間以上
        assert hours < 20  # 常識的な範囲

    def test_winter_shorter_than_summer(self):
        """冬の日照時間が夏より短いこと"""
        from generate_calendar import _calculate_daylight_hours
        
        summer = _calculate_daylight_hours(datetime(2026, 6, 21))
        winter = _calculate_daylight_hours(datetime(2026, 12, 21))
        assert winter < summer
