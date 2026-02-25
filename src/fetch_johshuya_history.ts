import * as fs from 'fs';
import * as path from 'path';
import { scrapeJohshuyaPage, JohshuyaFishingData } from './scraper_johshuya';

const SAVE_PATH = path.join(__dirname, '../data/johshuya_history.json');
const MAX_PAGES = 60; // とりあえず全件

const delay = (ms: number) => new Promise(res => setTimeout(res, ms));

async function main() {
    console.log('📦 上州屋の釣果情報（全件）の取得を開始します...');

    let allData: JohshuyaFishingData[] = [];
    if (fs.existsSync(SAVE_PATH)) {
        try {
            allData = JSON.parse(fs.readFileSync(SAVE_PATH, 'utf-8'));
            console.log(`📜 既存データ: ${allData.length} 件`);
        } catch (e) { }
    }

    const existingDates = new Set(allData.map(d => `${d.date}-${d.shopName}-${d.place}`));

    let newCount = 0;

    for (let page = 1; page <= MAX_PAGES; page++) {
        try {
            const pageData = await scrapeJohshuyaPage(page);
            if (pageData.length === 0) {
                console.log(`⏹ ページ ${page} にデータがないため終了します。`);
                break;
            }

            let pageHasNewData = false;
            for (const d of pageData) {
                const key = `${d.date}-${d.shopName}-${d.place}`;
                if (!existingDates.has(key)) {
                    allData.push(d);
                    existingDates.add(key);
                    newCount++;
                    pageHasNewData = true;
                }
            }

            console.log(`📄 Page ${page}: ${pageData.length} 件取得 (新規: ${newCount} 件)`);

            // 全件取得の場合は既存があっても続ける（上州屋はページ内の並びが厳密な日付順でない可能性があるため）

            await delay(300);
        } catch (e) {
            console.error(`❌ Page ${page} の取得に失敗しました:`, e);
            break;
        }
    }

    // 保存
    allData.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    fs.writeFileSync(SAVE_PATH, JSON.stringify(allData, null, 2), 'utf-8');

    console.log(`\n✅ 完了！合計: ${allData.length} 件 (新規追加: ${newCount} 件)`);

    // 海/淡水の集計
    const seaCount = allData.filter(d => d.category === 'sea').length;
    const freshCount = allData.filter(d => d.category === 'freshwater').length;
    const unknownCount = allData.filter(d => d.category === 'unknown').length;

    console.log(`📊 内訳: 海 ${seaCount}, 淡水 ${freshCount}, 不明 ${unknownCount}`);
}

main().catch(console.error);
