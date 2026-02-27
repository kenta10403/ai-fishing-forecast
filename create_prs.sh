set -e

# 特定のファイルだけをaddして一時コミットを作る（ここで未追跡の新規ファイルも追跡される）
git add src/scraper_johshuya.ts tests/test_johshuya_parse.ts scripts/clean_johshuya_data.ts data/johshuya_history.json data/fishing_forecast.db src/ml/dataset_real_marine.py src/ml/dataset_d.py src/ml/train_real_marine.py src/ml/model_catch_forecast_real.pkl src/ml/model_marine_env_real.pkl src/ml/model_trend.pkl src/ml/analyze_fishing_factors.py src/ml/generate_calendar.py src/ml/config.py scripts/fetch_openmeteo_history.py src/data/frontend_calendar.json
git commit -m "temp_all_changes"
git branch temp_branch

# mainの余計な変更を消して綺麗な状態に戻す
git reset --hard origin/main

# PR 1
git checkout -b fix/issue-1 main
git checkout temp_branch -- src/scraper_johshuya.ts tests/test_johshuya_parse.ts scripts/clean_johshuya_data.ts data/johshuya_history.json data/fishing_forecast.db
git commit -m "fix(scraper): 【Issue #1】釣果数の範囲表記パースバグ修正とデータクレンジング"
git push -u origin fix/issue-1
gh pr create --title "fix: 釣果数の範囲表記パースバグ修正と異常データクレンジング (Issue #1)" --body "Issue #1 の対応です。釣果数のパースで範囲表記の際に下限値を取得するよう修正し、過去データのクレンジングを実施しました。"

# PR 2
git checkout -b feature/model-dataset-improvements main
git checkout temp_branch -- src/ml/dataset_real_marine.py src/ml/dataset_d.py src/ml/train_real_marine.py src/ml/model_catch_forecast_real.pkl src/ml/model_marine_env_real.pkl src/ml/model_trend.pkl src/ml/analyze_fishing_factors.py
git commit -m "feat(ml): 【Issue #2,3,4】海況データフィルタ修正、CPUE導入、黒潮期間の補正"
git push -u origin feature/model-dataset-improvements
gh pr create --title "feat: データ抽出処理とモデル推論性能の向上 (Issue #2, #3, #4)" --body "Issue #2, #3, #4 の統合対応です。対象エリアのジオフィルタリング、CPUE指標への変更、黒潮大蛇行フラグ日時の修正と、それに伴うモデル再学習を実施しました。"

# PR 3
git checkout -b fix/inference-calendar-logic main
git checkout temp_branch -- src/ml/generate_calendar.py src/ml/config.py scripts/fetch_openmeteo_history.py src/data/frontend_calendar.json
git commit -m "fix(inference): 【Issue #5-10】推論時のパラメータ参照と計算ロジック改善"
git push -u origin fix/inference-calendar-logic
gh pr create --title "fix: カレンダー推論APIの精度と整合性向上 (Issue #5 - #10)" --body "Issue #5 から #10 までの対応です。初期値のDB化、潮汐履歴からの参照、風速・日照時間のAPIパラメータ最適化、座標統合を行いました。"

# クリーンアップ
git checkout main
git branch -D temp_branch

echo "✅ すべてのPRの作成が完了しました！"
