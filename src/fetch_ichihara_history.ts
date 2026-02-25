import * as fs from 'fs';
import * as path from 'path';
import { scrapeIchiharaLinks } from './scraper_ichihara_list';
import { scrapeIchiharaDetail } from './scraper_ichihara_detail';
import { FishingData } from './scraper';

const SAVE_PATH = path.join(__dirname, '../data/ichihara_2024_to_present.json');

// 遅延実行用のヘルパー関数
const delay = (ms: number) => new Promise(res => setTimeout(res, ms));

interface IchiharaJsonFormat {
    metadata: {
        last_fetched_date: string;
        facility: string;
        updated_at: string;
    };
    data: FishingData[];
}

async function main() {
    console.log('🎣 市原市海づり公園のデータ同期を開始します...');

    let existingJson: IchiharaJsonFormat | null = null;
    let allData: FishingData[] = [];
    let lastDate = '2024/01/01'; // デフォルトの開始日

    if (fs.existsSync(SAVE_PATH)) {
        try {
            const raw = fs.readFileSync(SAVE_PATH, 'utf-8');
            existingJson = JSON.parse(raw);
            if (existingJson && existingJson.data) {
                allData = existingJson.data;
                lastDate = existingJson.metadata.last_fetched_date;
                console.log(`📜 既存データを確認: ${allData.length} 件保存済み (最新: ${lastDate})`);
            }
        } catch (e) {
            console.warn('⚠️ 既存データのパースに失敗しました。新規で開始します。');
        }
    }

    // 1. 最新分を取得するため、最初の方は全走査。既に保存済みの最新日付に到達したら止める
    console.log('1. URLの収集を開始します...');
    const allUrls = await scrapeIchiharaLinks(1, 250);
    console.log(`✅ 合計 ${allUrls.length} 件のURL候補を取得しました。\n`);

    const existingDates = new Set(allData.map(d => d.date));
    let successCount = 0;
    let emptyCount = 0;
    let errorCount = 0;
    let skipCount = 0;
    let reachedLastPoint = false;

    console.log('2. 詳細データの取得とマージを開始します...');
    for (let i = 0; i < allUrls.length; i++) {
        const url = allUrls[i];

        try {
            const data = await scrapeIchiharaDetail(url);

            if (data) {
                // 既に存在する日付なら、それ以上遡る必要がないかチェック
                if (existingDates.has(data.date)) {
                    // 最新取得日と同じ、あるいはそれより古いデータに遭遇した場合
                    // 新規追加分のみを取るモードならここでbreakできるが、抜け漏れ防止のため一旦skipで進む
                    console.log(`[${i + 1}/${allUrls.length}] Skip (Existing): ${data.date}`);
                    skipCount++;

                    // 最新取得日以前のデータが連続して見つかるようなら、概ね完了とみなす
                    // （市原は1日に1記事なので、日付が被る＝既に取得済み）
                    if (data.date <= lastDate && skipCount > 10) {
                        console.log(`🏁 最新取得日 (${lastDate}) 以前のデータに十分到達したため、収集を終了します。`);
                        reachedLastPoint = true;
                        break;
                    }
                    continue;
                }

                // 2023年以前のデータになったら終了する
                if (data.date.startsWith('2023/') || data.date.startsWith('2022/')) {
                    console.log(`📅 2023年以前のデータ (${data.date}) に到達したため、取得を停止します。`);
                    break;
                }

                console.log(`[${i + 1}/${allUrls.length}] Fetching ${url} ...`);
                allData.push(data);
                if (data.catches.length > 0) {
                    console.log(`  ✅ Success (${data.date}): ${data.catches.length} catches`);
                    successCount++;
                } else {
                    console.log(`  ➖ Empty (${data.date}): No catches recorded`);
                    emptyCount++;
                }
            }
        } catch (e) {
            console.error(`[${i + 1}/${allUrls.length}] ❌ Error: ${url}`, e);
            errorCount++;
        }

        await delay(200);
    }

    // 3. データを日付順にソートして、最新日付をメタデータに更新
    console.log('\n3. ファイルへの保存を開始します...');
    allData.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

    const newLastDate = allData.length > 0 ? allData[0].date : lastDate;

    const output: IchiharaJsonFormat = {
        metadata: {
            last_fetched_date: newLastDate,
            facility: 'ichihara',
            updated_at: new Date().toISOString()
        },
        data: allData
    };

    fs.writeFileSync(SAVE_PATH, JSON.stringify(output, null, 2), 'utf-8');

    // 完了報告
    console.log('\n=======================================');
    console.log(`🎉 完了: 市原市海づり公園 (ichihara)`);
    console.log(`📊 新規取得: ${successCount + emptyCount} 件`);
    console.log(`⏩ スキップ: ${skipCount} 件`);
    console.log(`❌ エラー: ${errorCount} 件`);
    console.log(`📁 保存先: ${SAVE_PATH}`);
    console.log(`📈 最新日付: ${newLastDate} (合計: ${allData.length} 件)`);
    console.log('=======================================');
}

if (require.main === module) {
    main().catch(console.error);
}
