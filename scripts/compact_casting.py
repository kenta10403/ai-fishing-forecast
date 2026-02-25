#!/usr/bin/env python3
"""
casting_choka の巨大JSONを日別・エリア別にまとめて軽量化するスクリプト。

処理内容:
- 日付 × エリア × カテゴリ でグループ化
- 同じ魚種の釣果は count を合算
- 不要なフィールド（shopName, size）を削除
- size フィールド内に匹数情報があれば count に反映
- 差分処理対応: 前回どこまで処理したかを記録し、次回は新しいデータだけ処理

使い方:
  python3 scripts/compact_casting.py                    # full + resume を全てまとめる
  python3 scripts/compact_casting.py --incremental      # 差分だけ追記
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Input files (処理対象)
INPUT_FILES = [
    "casting_choka_full.json",
    "casting_choka_resume.json",
]

# Output file (まとめ済みデータ)
OUTPUT_FILE = os.path.join(DATA_DIR, "casting_compact.json")

# 差分管理用メタデータ
META_FILE = os.path.join(DATA_DIR, ".compact_meta.json")


def extract_count_from_size(size_str: str) -> int:
    """
    size フィールドから匹数を抽出する。
    例: "20～25cm 5匹" → 5
        "30cm 1本" → 1
        "15～20cm" → 0 (匹数情報なし)
    """
    if not size_str:
        return 0

    # "XX匹" or "XX本" or "XX尾" のパターンを探す
    match = re.search(r'(\d+)\s*[匹本尾]', size_str)
    if match:
        return int(match.group(1))

    return 0


def load_json_streaming(filepath: str):
    """
    大きなJSONファイルをストリーミングで読み込む。
    メモリ効率のため、ijson が使えればそちらを使う。
    なければ通常の json.load を使う。
    """
    print(f"  Loading {os.path.basename(filepath)} ({os.path.getsize(filepath) / (1024*1024):.1f}MB)...")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
        return [data]
    elif isinstance(data, list):
        return data
    return []


def compact_records(records: list, skip_before_date: str = None) -> dict:
    """
    レコードを日付 × エリア × カテゴリでグループ化し、同じ魚種の釣果を合算する。

    Returns:
        dict: {
            "2025/01/15_神奈川県_sea": {
                "date": "2025/01/15",
                "area": "神奈川県",
                "category": "sea",
                "catches": [{"name": "アジ", "count": 150}, ...],
                "report_count": 5  # 元の報告件数
            },
            ...
        }
    """
    groups = {}
    skipped = 0
    processed = 0

    for record in records:
        if not isinstance(record, dict):
            continue

        date = record.get("date", "")
        if not date:
            date = record.get("fishingDate", "")
        if not date:
            continue

        # 差分処理: skip_before_date より前のレコードはスキップ
        if skip_before_date and date <= skip_before_date:
            skipped += 1
            continue

        area = record.get("area", "不明")
        category = record.get("category", "unknown")

        group_key = f"{date}_{area}_{category}"

        if group_key not in groups:
            groups[group_key] = {
                "date": date,
                "area": area,
                "category": category,
                "catches": {},
                "report_count": 0,
            }

        group = groups[group_key]
        group["report_count"] += 1

        catches = record.get("catches", [])
        for catch in catches:
            name = catch.get("name", "不明")
            count = 0

            # count フィールドから取得
            try:
                count = int(catch.get("count") or 0)
            except (ValueError, TypeError):
                count = 0

            # size フィールドから匹数を抽出して加算
            size_str = catch.get("size", "")
            size_count = extract_count_from_size(size_str)
            if size_count > 0 and count == 0:
                count = size_count

            if count <= 0:
                count = 1  # 最低1匹は釣れている（報告がある以上）

            if name in group["catches"]:
                group["catches"][name] += count
            else:
                group["catches"][name] = count

        processed += 1

    if skipped > 0:
        print(f"  Skipped {skipped} records (before {skip_before_date})")
    print(f"  Processed {processed} records → {len(groups)} groups")

    return groups


def groups_to_list(groups: dict) -> list:
    """グループ化されたデータをリスト形式に変換"""
    result = []
    for group in groups.values():
        entry = {
            "date": group["date"],
            "area": group["area"],
            "category": group["category"],
            "report_count": group["report_count"],
            "catches": [
                {"name": name, "count": count}
                for name, count in sorted(group["catches"].items(), key=lambda x: -x[1])
            ],
        }
        result.append(entry)

    # 日付でソート
    result.sort(key=lambda x: x["date"])
    return result


def load_meta() -> dict:
    """差分管理用のメタデータを読み込む"""
    if os.path.exists(META_FILE):
        with open(META_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_meta(meta: dict):
    """差分管理用のメタデータを保存"""
    with open(META_FILE, 'w') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def main():
    incremental = "--incremental" in sys.argv

    print("=== Casting Data Compactor ===")
    print(f"Mode: {'差分処理' if incremental else 'フル処理'}")
    print()

    meta = load_meta()
    skip_before_date = None

    if incremental:
        skip_before_date = meta.get("last_processed_date")
        if skip_before_date:
            print(f"前回の処理日: {skip_before_date} 以降のデータを処理します")
        else:
            print("メタデータが見つかりません。フル処理を実行します")
            incremental = False

    all_groups = {}
    latest_date = ""

    # 差分モードの場合、既存のcompactデータを先に読み込む
    if incremental and os.path.exists(OUTPUT_FILE):
        print(f"既存のcompactデータを読み込み中...")
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        for entry in existing:
            key = f"{entry['date']}_{entry['area']}_{entry['category']}"
            all_groups[key] = {
                "date": entry["date"],
                "area": entry["area"],
                "category": entry["category"],
                "catches": {c["name"]: c["count"] for c in entry.get("catches", [])},
                "report_count": entry.get("report_count", 0),
            }
        print(f"  既存データ: {len(all_groups)} groups")

    for input_file in INPUT_FILES:
        filepath = os.path.join(DATA_DIR, input_file)
        if not os.path.exists(filepath):
            print(f"  SKIP: {input_file} (ファイルなし)")
            continue

        print(f"\n処理中: {input_file}")
        records = load_json_streaming(filepath)
        new_groups = compact_records(records, skip_before_date if incremental else None)

        # マージ
        for key, group in new_groups.items():
            if key in all_groups:
                existing = all_groups[key]
                existing["report_count"] += group["report_count"]
                for name, count in group["catches"].items():
                    if name in existing["catches"]:
                        existing["catches"][name] += count
                    else:
                        existing["catches"][name] = count
            else:
                all_groups[key] = group

            if group["date"] > latest_date:
                latest_date = group["date"]

    # リスト化して保存
    result = groups_to_list(all_groups)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    output_size = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    input_total = sum(
        os.path.getsize(os.path.join(DATA_DIR, f))
        for f in INPUT_FILES
        if os.path.exists(os.path.join(DATA_DIR, f))
    ) / (1024 * 1024)

    print(f"\n=== 完了 ===")
    print(f"入力合計: {input_total:.1f}MB")
    print(f"出力: {OUTPUT_FILE} ({output_size:.1f}MB)")
    print(f"圧縮率: {(1 - output_size / input_total) * 100:.1f}% 削減")
    print(f"グループ数: {len(result)}")
    print(f"最新日付: {latest_date}")

    # メタデータ更新
    save_meta({
        "last_processed_date": latest_date,
        "last_run": datetime.now().isoformat(),
        "input_files": INPUT_FILES,
        "groups_count": len(result),
    })
    print(f"メタデータを {META_FILE} に保存しました")


if __name__ == "__main__":
    main()
