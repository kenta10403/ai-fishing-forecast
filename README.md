# AI釣果予報 (AI Fishing Forecast)

データドリブンな2段階AIモデルを利用した、東京湾および荒川等の釣果・海況予測システムです。

## セットアップ手順

### 1. リポジトリのクローンと環境構築

```bash
git clone https://github.com/kenta10403/ai-fishing-forecast.git
cd ai-fishing-forecast

# 仮想環境の作成とアクティベート (Python 3.10以降推奨)
python -m venv venv
source venv/bin/activate  # Windows の場合は venv\Scripts\activate

# 依存パッケージのインストール
pip install -r requirements.txt
```

### 2. 環境変数 (.env) の設定

本システムでは、高精度な海況予測モデル（波高・海面水温）のために [Copernicus Marine Service](https://marine.copernicus.eu/) のAPIを利用します。
Copernicusのデータを利用するには、無料のユーザー登録とクレデンシャルの設定が必要です。

1. [Copernicus Registration](https://data.marine.copernicus.eu/register) でアカウントを作成します。
2. リポジトリ内の `.env.example` をコピーして `.env` を作成します。
   ```bash
   cp .env.example .env
   ```
3. `.env` ファイルに作成したアカウントのユーザー名・パスワードを記述します。
   ```env
   COPERNICUS_MARINE_USERNAME=your_username
   COPERNICUS_MARINE_PASSWORD=your_password
   ```

> ※ APIを利用しない（`.env`を設定しない）場合でもフォールバックとしてエラーを回避し処理は続行されますが、推論にSSTや波高データが必要なため精度に影響が出ます。

### 3. データ移行およびデータベース設定 (初回のみ)

データソースの刷新に伴い、既存のOpen-Meteoテーブルからメタデータを変更するマイグレーションが必要です。

```bash
python scripts/migrate_table_name.py
```
> ※ これにより `openmeteo_marine_history` テーブルが `marine_forecast_history` へとリネームされ、アプリケーション内で利用可能な状態になります。

必要に応じて、過去データを取得するスクリプトを実行してください。
- Copernicusの過去海況データの一括取得: `python scripts/fetch_copernicus_marine.py`
- 国交省データベースの河川流量CSV取込: `python scripts/fetch_mlit_river_data.py <csv_file_path>`

---

## テストの実行

機能追加やロジック変更の検証には `pytest` を使用します。
APIのパースロジック、移動平均減衰ロジック、日照時間計算処理などがテスト対象になっています。

```bash
# プロジェクトルートで実行
pytest tests/ -v
```

---

## 各種ドキュメントについて
プロジェクトで使用している各データの起源やDB構成については、`docs/data_sources.md` を参照してください。
AI推論時の設計指針（Data Leakage防止や掟など）については `AI_DESIGN_GUIDELINES.md` を確認してください。
