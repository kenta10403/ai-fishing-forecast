"""
generate_calendar.py のテストケース
スコア計算ロジック、月ごとのスコア分布、データ整合性を検証する。
"""
import sys
import os
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'ml'))

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'src', 'data')
CALENDAR_JSON = os.path.join(DATA_DIR, 'frontend_calendar.json')


@pytest.fixture
def calendar_data():
    """生成済みのカレンダーJSONを読み込む"""
    if not os.path.exists(CALENDAR_JSON):
        pytest.skip("frontend_calendar.json が生成されていません。先に generate_calendar.py を実行してください。")
    with open(CALENDAR_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestCalendarDataIntegrity:
    """カレンダーデータの整合性テスト"""

    def test_not_empty(self, calendar_data):
        """データが空でないこと"""
        assert len(calendar_data) > 0

    def test_required_fields(self, calendar_data):
        """各日付に必須フィールドが存在すること"""
        required = ['date', 'type', 'score', 'weather', 'tide', 'trend', 'details']
        for entry in calendar_data:
            for field in required:
                assert field in entry, f"日付 {entry.get('date', '?')} にフィールド '{field}' がありません"

    def test_score_range(self, calendar_data):
        """全スコアが 5〜100 の範囲であること"""
        for entry in calendar_data:
            assert 5 <= entry['score'] <= 100, \
                f"日付 {entry['date']} のスコア {entry['score']} が範囲外です"

    def test_valid_weather(self, calendar_data):
        """天気が有効な値であること"""
        valid_weather = {'sunny', 'cloudy', 'rain', 'windy'}
        for entry in calendar_data:
            assert entry['weather'] in valid_weather, \
                f"日付 {entry['date']} の天気 '{entry['weather']}' が不正です"

    def test_valid_tide(self, calendar_data):
        """潮回りが有効な値であること"""
        valid_tides = {'大潮', '中潮', '小潮', '長潮', '若潮'}
        for entry in calendar_data:
            assert entry['tide'] in valid_tides, \
                f"日付 {entry['date']} の潮回り '{entry['tide']}' が不正です"

    def test_valid_trend(self, calendar_data):
        """トレンドが有効な値であること"""
        valid_trends = {'fire', 'hot', 'normal', 'bad'}
        for entry in calendar_data:
            assert entry['trend'] in valid_trends, \
                f"日付 {entry['date']} のトレンド '{entry['trend']}' が不正です"

    def test_valid_type(self, calendar_data):
        """日付タイプが有効な値であること"""
        valid_types = {'past', 'forecast', 'base'}
        for entry in calendar_data:
            assert entry['type'] in valid_types, \
                f"日付 {entry['date']} のタイプ '{entry['type']}' が不正です"


class TestMonthlyScoreDistribution:
    """月ごとのスコア分布が妥当であるかのテスト"""

    def _group_by_month(self, calendar_data):
        """カレンダーデータを月ごとにグループ化"""
        months = {}
        for entry in calendar_data:
            parts = entry['date'].split('/')
            month_key = f"{parts[0]}/{parts[1]}"
            if month_key not in months:
                months[month_key] = []
            months[month_key].append(entry['score'])
        return months

    def test_no_constant_scores_within_month(self, calendar_data):
        """同月内のスコアが全て同じではないこと（変化があるべき）"""
        months = self._group_by_month(calendar_data)
        for month, scores in months.items():
            if len(scores) > 5:
                unique_scores = set(scores)
                assert len(unique_scores) > 1, \
                    f"{month} のスコアが全て {scores[0]} で固定されています"

    def test_no_extreme_month_to_month_jump(self, calendar_data):
        """隣接月の平均スコア差が50以上にならないこと"""
        months = self._group_by_month(calendar_data)
        sorted_months = sorted(months.keys())
        for i in range(1, len(sorted_months)):
            prev_avg = sum(months[sorted_months[i-1]]) / len(months[sorted_months[i-1]])
            curr_avg = sum(months[sorted_months[i]]) / len(months[sorted_months[i]])
            diff = abs(curr_avg - prev_avg)
            assert diff < 50, \
                f"{sorted_months[i-1]} → {sorted_months[i]} で平均スコアが {diff:.1f} 点ジャンプしています"

    def test_winter_lower_than_autumn(self, calendar_data):
        """冬（1-2月）の平均スコアが秋（9-10月）より低いこと"""
        months = self._group_by_month(calendar_data)
        winter_scores = []
        autumn_scores = []
        for month_key, scores in months.items():
            month_num = int(month_key.split('/')[1])
            if month_num in [1, 2]:
                winter_scores.extend(scores)
            elif month_num in [9, 10]:
                autumn_scores.extend(scores)
        
        if winter_scores and autumn_scores:
            winter_avg = sum(winter_scores) / len(winter_scores)
            autumn_avg = sum(autumn_scores) / len(autumn_scores)
            assert winter_avg < autumn_avg, \
                f"冬の平均({winter_avg:.1f})が秋の平均({autumn_avg:.1f})を上回っています"

    def test_no_day_to_day_cliff(self, calendar_data):
        """連続する日で40点以上のスコア落差がないこと"""
        for i in range(1, len(calendar_data)):
            prev = calendar_data[i - 1]
            curr = calendar_data[i]
            diff = abs(curr['score'] - prev['score'])
            # 月の境界は除外（違う性質のデータの可能性）
            if diff >= 40:
                prev_month = prev['date'].split('/')[1]
                curr_month = curr['date'].split('/')[1]
                if prev_month == curr_month:
                    assert False, \
                        f"{prev['date']} ({prev['score']}) → {curr['date']} ({curr['score']}) で {diff} 点の急落/急騰"

    def test_annual_average_near_50(self, calendar_data):
        """年間の平均スコアが30〜70の範囲内であること"""
        all_scores = [e['score'] for e in calendar_data]
        avg = sum(all_scores) / len(all_scores)
        assert 30 <= avg <= 70, \
            f"年間平均スコアが {avg:.1f} で、30〜70 の範囲外です"
