# AI開発指示書 (AI.md)

このプロジェクト「AI釣果予報 (ai-fishing-forecast)」を他のAIツールやLLMで開発・メンテナンスするためのガイドラインやで。

## 📋 プロジェクト概要
首都圏近郊の海づり施設（本牧・大黒・磯子・市原）の釣果データを収集し、将来の釣果を予測するための基盤。
- **言語**: TypeScript (Node.js)
- **パッケージマネージャー**: pnpm
- **実行環境**: tsx

## 📁 ディレクトリ構造
- `src/`: ソースコード
  - `scraper.ts`: 共通型定義と横浜3施設のAPI連携
  - `fetch_history.ts`: 横浜3施設の過去データ一括取得
  - `scraper_ichihara_list.ts`: 市原の一覧取得
  - `scraper_ichihara_detail.ts`: 市原の詳細パース（重要：詳細な環境データを抽出）
  - `fetch_ichihara_history.ts`: 市原の差分更新バッチ
- `data/`: 取得済みJSONデータ
  - 各ファイルは `metadata` (最新取得日) と `data` (釣果配列) の構造を持つ。

## 🛠 開発ルール
1. **差分更新**: データ取得時は `metadata.last_fetched_date` を参照し、それ以降のデータのみを取得する「レジューム機能」を維持すること。
2. **市原パース**: 市原のサイトはDOM構造が変わりやすいため、`scraper_ichihara_detail.ts` のセレクタ修正時は `npx tsx src/scraper_ichihara_detail.ts` でテスト実行して確認すること。
3. **環境変数**: APIキーなどの機密情報は `.env` に逃がし、`process.env.APPSYNC_API_KEY` 等で取得すること。
4. **型定義**: 新しい項目を追加する場合は `src/scraper.ts` の `FishingData` インターフェースを拡張すること。

## 🔄 データ更新フロー
- **横浜**: `npx tsx src/fetch_history.ts`
- **市原**: `npx tsx src/fetch_ichihara_history.ts`

## ⚠️ 注意点
- 市原の2024年3月以前のデータはサーバー上に存在しないため、スキャンの下限は `2024/03/01` とする。
- サーバー負荷軽減のため、リクエスト間には必ず `200ms` 以上のディレイを入れること。
