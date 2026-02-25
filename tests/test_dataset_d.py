"""
dataset_d.py のテストケース
データのロード、前処理、バイアス補正が正しく機能するか検証する。
"""
import sys
import os
import pytest
import pandas as pd
import numpy as np

# src/ml をパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'ml'))
from dataset_d import load_trend_data, preprocess_trend_data, TARGET_SPECIES_LIST


class TestLoadTrendData:
    """load_trend_data の基本動作テスト"""

    def test_returns_dataframe(self):
        """返り値がDataFrameであること"""
        df = load_trend_data()
        assert isinstance(df, pd.DataFrame)

    def test_not_empty(self):
        """データが空でないこと"""
        df = load_trend_data()
        assert len(df) > 0, "トレンドデータが空です。データファイルを確認してください。"

    def test_required_columns_exist(self):
        """必須カラムが存在すること"""
        df = load_trend_data()
        required = ['date', 'area', 'weather', 'species', 'trend_score', 'weight']
        for col in required:
            assert col in df.columns, f"必須カラム '{col}' が見つかりません"

    def test_kanto_only(self):
        """関東圏のデータのみであること"""
        df = load_trend_data()
        kanto = ["東京都", "神奈川県", "千葉県", "埼玉県", "茨城県", "栃木県", "群馬県"]
        invalid_areas = df[~df['area'].isin(kanto)]['area'].unique()
        assert len(invalid_areas) == 0, f"関東圏外のエリアが含まれています: {invalid_areas}"

    def test_target_species_only(self):
        """対象魚種のみが含まれていること"""
        df = load_trend_data()
        # 名寄せ後のリスト（シーバス→スズキ、チヌ→クロダイ等）
        valid = set(TARGET_SPECIES_LIST) - {"シーバス", "チヌ", "ワラサ", "ブリ"}
        invalid_species = df[~df['species'].isin(valid)]['species'].unique()
        assert len(invalid_species) == 0, f"対象外の魚種が含まれています: {invalid_species}"

    def test_facility_weight_higher(self):
        """施設データの重みが釣具屋より高いこと"""
        df = load_trend_data()
        facility_rows = df[df['is_facility'] == True]
        shop_rows = df[df['is_facility'] == False]
        if len(facility_rows) > 0 and len(shop_rows) > 0:
            assert facility_rows['weight'].mean() > shop_rows['weight'].mean(), \
                "施設データの重みが釣具屋データ以上であるべきです"

    def test_no_extreme_outliers(self):
        """極端な外れ値が除去されていること"""
        df = load_trend_data()
        q99 = df['trend_score'].quantile(0.99)
        q01 = df['trend_score'].quantile(0.01)
        # 外れ値除去後なので、99%と1%の差が元データの10倍以上にならないはず
        assert q99 / max(q01, 0.01) < 1000, "外れ値除去後もスコアの範囲が広すぎます"

    def test_trend_score_positive(self):
        """トレンドスコアが正の値であること"""
        df = load_trend_data()
        assert (df['trend_score'] >= 0).all(), "負のトレンドスコアが含まれています"


class TestPreprocessTrendData:
    """preprocess_trend_data の基本動作テスト"""

    @pytest.fixture
    def raw_data(self):
        return load_trend_data()

    def test_returns_tuple(self, raw_data):
        """返り値が (X, y) のタプルであること"""
        result = preprocess_trend_data(raw_data)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_x_y_same_length(self, raw_data):
        """X と y の行数が一致すること"""
        X, y = preprocess_trend_data(raw_data)
        assert len(X) == len(y)

    def test_no_nan_in_features(self, raw_data):
        """特徴量にNaNが含まれないこと"""
        X, y = preprocess_trend_data(raw_data)
        assert X.isna().sum().sum() == 0, f"NaN含有カラム: {X.columns[X.isna().any()].tolist()}"

    def test_period_of_year_range(self, raw_data):
        """period_of_year が 1〜36 の範囲であること"""
        X, y = preprocess_trend_data(raw_data)
        if 'period_of_year' in X.columns:
            assert X['period_of_year'].min() >= 1
            assert X['period_of_year'].max() <= 36

    def test_day_of_week_range(self, raw_data):
        """day_of_week が 0〜6 の範囲であること"""
        X, y = preprocess_trend_data(raw_data)
        if 'day_of_week' in X.columns:
            assert X['day_of_week'].min() >= 0
            assert X['day_of_week'].max() <= 6


class TestBiasCorrection:
    """バイアス補正のテスト"""

    def test_weekday_normalization(self):
        """曜日バイアスが軽減されていること"""
        df = load_trend_data()
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df['dow'] = df['date'].dt.dayofweek
        
        weekday_avg = df[df['dow'].between(0, 4)]['trend_score'].mean()
        weekend_avg = df[df['dow'].between(5, 6)]['trend_score'].mean()
        
        if weekday_avg > 0 and weekend_avg > 0:
            # 正規化後は土日と平日の差が3倍以内であるべき
            ratio = max(weekday_avg, weekend_avg) / min(weekday_avg, weekend_avg)
            assert ratio < 3.0, f"曜日バイアスが大きすぎます (平日/土日比: {ratio:.2f})"

    def test_no_duplicate_records(self):
        """同じ日付/エリア/魚種の重複がないこと"""
        df = load_trend_data()
        dups = df.duplicated(subset=['date', 'area', 'species'], keep=False)
        assert dups.sum() == 0, f"重複レコードが {dups.sum()} 件あります"
