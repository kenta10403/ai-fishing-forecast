# 海況・気象データソース一覧 (Data Source Inventory)

AI予測モデルに使用している各データの格納先、一次ソース、および取得状況のまとめです。

| 項目グループ | 具体的な項目名 | 格納先DBテーブル | **データの一次ソース (Origin)** | 頻度と役割 |
| :--- | :--- | :--- | :--- | :--- |
| **気象・陸上** | 気温、風速、降水量、日照時間 | `weather_history` | **MET Norway API** | 日次で充足。商用OK。高精度データ。 |
| **潮汐** | 潮回り（大潮〜若潮）、潮位 | `tide_history` | AppSync API (独自システム) | 変更なし（現状維持）。 |
| **波浪** | 波高、波向き | `marine_forecast_history` | **Copernicus Marine** | 商用OK。旧 `openmeteo_marine_history` からリネーム。 |
| **河川** | 河川流量（荒川等） | `marine_forecast_history` / `river_discharge_history` | **国土交通省 水文水質データベース** | 過去データはCSVバルクインポート。推論時は移動平均減衰。 |
| **海流フラグ** | 黒潮大蛇行フラグ | (計算ロジック) | 海上保安庁等の発表定義 | 変更なし。 |
| **水質 (重要)** | 海面水温 (SST)、塩分濃度、DO、流向・流速 | `tokyo_bay_marine_data` | **東京湾環境情報センター (TBEIC)** | **学習用(Train)**: 各観測塔から日次で自動同期。 |
| **水質 (予報)** | 海面水温 (SST) | (Copernicus API直接) | **Copernicus Marine** | **推論用(Serving)**: 10日予報時のAPI直接取得。 |
| **水質 (参考)** | 透明度、COD等 | `tokyo_bay_marine_data` | 千葉県環境生活部 (補完用) | 変更なし。不定期更新。 |

## データ取得の仕組み
- **MET Norway API**: `src/ml/generate_calendar.py` の `_fetch_met_norway_weather()` で Locationforecast 2.0 API を呼び出し。
- **Copernicus Marine**: `src/ml/generate_calendar.py` の `_fetch_copernicus_marine()` で波高・SST予報を取得。過去データは `scripts/fetch_copernicus_marine.py` でバルク取得。
- **TBEIC 同期**: `scripts/sync_tbeic_marine_data.py` により、東京湾内の主要な観測塔の連続観測データを取得。
- **河川流量**: `scripts/fetch_mlit_river_data.py` で国交省CSVをインポート。推論時は降水予報連動の移動平均減衰ロジックで将来値をシミュレーション。

## 今後の改善・検討事項
- **データ欠損への対応**: 観測塔のメンテナンス等による欠損時の補完ロジックの強化。
- **予測精度のフィードバック**: 取得した実測データを用いた、過去の予測値の精度検証パイプラインの構築。
