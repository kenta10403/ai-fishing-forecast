# AI開発指示書 (AI.md)

このプロジェクト「AI釣果予報 (ai-fishing-forecast)」を他のAIツールやLLMで開発・メンテナンスするためのガイドラインです。

## 📋 プロジェクト概要
首都圏近郊の海づり施設（本牧・大黒・磯子・市原）の釣果データを自動収集し、将来の釣果を予測するための基盤システムです。
- **言語**: TypeScript (Node.js)
- **パッケージマネージャー**: pnpm
- **実行環境**: tsx

## 📁 ディレクトリ構造
- `src/`: ソースコード
  - `scraper.ts`: 共通型定義および横浜3施設のAPI連携ロジック。
  - `fetch_history.ts`: 横浜3施設の過去データ一括取得スクリプト。
  - `scraper_ichihara_list.ts`: 市原の一覧取得用。
  - `scraper_ichihara_detail.ts`: 市原の詳細データ抽出用（環境データ取得の実装を含む）。
  - `fetch_ichihara_history.ts`: 市原の差分更新バッチ。
- `data/`: 取得済みJSONデータ
  - 各ファイルは `metadata` (最新取得日等) と `data` (釣果配列) の構造を持ちます。

## 🛠 開発ルール
1. **差分更新**: データ取得時は `metadata.last_fetched_date` を参照し、それ以降のデータのみを追加取得する「レジューム機能」を維持してください。
2. **市原パース**: 市原のサイトはDOM構造が変動しやすいため、セレクタ修正時は `npx tsx src/scraper_ichihara_detail.ts` でテスト実行を確認してください。
3. **機密情報の管理**: APIキーなどの情報は `.env` ファイルに記述し、`process.env` を介して利用してください。
4. **型定義の継承**: データ構造を変更する場合は、`src/scraper.ts` の `FishingData` インターフェースを拡張してください。

## 🔄 データ更新フロー
- **横浜**: `npx tsx src/fetch_history.ts`
- **市原**: `npx tsx src/fetch_ichihara_history.ts`

## ⚠️ 注意事項
- 市原の2024年3月以前のデータはサーバー上に存在しないため、取得の下限は `2024/03/01` とします。
- サーバー負荷軽減のため、リクエスト間には必ず `200ms` 以上の遅延（delay）を入れてください。

## 🔮 機械学習による釣果予測
収集したデータを活用し、将来の「釣果期待値」を算出する機械学習パイプラインを実装済みです。

- **実行ディレクトリ**: `src/ml/`
- **言語と主なライブラリ**: Python (Scikit-learn, LightGBM, pandas等)
- **環境構築**: プロジェクトのルートディレクトリに仮想環境 (`venv`) を作成し、`requirements.txt` を用いて構築します。
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```
- **特徴量**: 
  - 取得したJSONデータから月、曜日、水温を抽出し、天気、施設、潮回りをOne-Hot Encodingで数値化して利用。
- **実装済みのスクリプト**: 
  - `dataset.py`: JSONからのデータ読み込みと前処理 (対象施設の絞り込み機能あり)
  - `train.py`: ランダムフォレスト等によるモデル学習および `model.pkl` の生成
  - `predict.py`: 学習済みモデルを用いた将来の釣果スコア予測

今後、モデルの精度改善や新しい手法の検証を行う際も、このディレクトリ構造とパイプラインを活用・拡張してください。
