import * as fs from 'fs';
import * as path from 'path';
import { scrapeJohshuyaPage, JohshuyaFishingData } from './scraper_johshuya';

const SAVE_PATH = path.join(__dirname, '../data/johshuya_history.json');
const LOG_PATH = path.join(__dirname, '../data/johshuya_history_fetch.log');
const START_YEAR = 2009;
const CURRENT_YEAR = new Date().getFullYear();

const delay = (ms: number) => new Promise(res => setTimeout(res, ms));

function logProgress(msg: string) {
    console.log(msg);
    fs.appendFileSync(LOG_PATH, `[${new Date().toISOString()}] ${msg}\n`, 'utf-8');
}

async function main() {
    logProgress(`🚀 上州屋の釣果情報（${START_YEAR}年〜現在）の全件取得を開始します...`);

    let allData: JohshuyaFishingData[] = [];
    if (fs.existsSync(SAVE_PATH)) {
        try {
            allData = JSON.parse(fs.readFileSync(SAVE_PATH, 'utf-8'));
            logProgress(`📜 既存データ: ${allData.length} 件`);
        } catch (e) {
            logProgress('⚠️ 既存データの読み込みに失敗したため、新規で開始します。');
        }
    }

    const existingKeys = new Set(allData.map(d => `${d.date}-${d.shopName}-${d.place}`));
    let newCount = 0;

    const RESUME_YEAR = 2022; // 中断した年から再開
    const RESUME_MONTH = 3;   // 中断した月から再開

    // 年・月ごとにループして取得（一気に取得するとページ上限に抵触するため）
    for (let year = RESUME_YEAR || CURRENT_YEAR; year >= START_YEAR; year--) {
        const startMonth = (year === RESUME_YEAR) ? RESUME_MONTH : (year === CURRENT_YEAR ? new Date().getMonth() + 1 : 12);
        const endMonth = (year === START_YEAR) ? 1 : 1; // 2009年は1月から（実際は途中からかもしれないが網羅的に）

        for (let month = startMonth; month >= endMonth; month--) {
            logProgress(`\n📅 --- ${year}年 ${month}月のデータを取得中 ---`);

            for (let page = 1; page <= 50; page++) { // 1ヶ月最大500件（50ページ）あれば十分
                try {
                    const pageData = await scrapeJohshuyaPage(page, year, month);

                    if (pageData.length === 0) {
                        logProgress(`⏹ ${year}年${month}月のページ ${page} にデータがないため、次の月に進みます。`);
                        break;
                    }

                    let pageNewCount = 0;
                    for (const d of pageData) {
                        const key = `${d.date}-${d.shopName}-${d.place}`;
                        if (!existingKeys.has(key)) {
                            allData.push(d);
                            existingKeys.add(key);
                            newCount++;
                            pageNewCount++;
                        }
                    }

                    logProgress(`📄 ${year}/${month} Page ${page}: ${pageData.length} 件中 ${pageNewCount} 件が新規`);

                    // サーバー負荷軽減
                    await delay(500);
                } catch (e) {
                    console.error(`❌ ${year}/${month} Page ${page} の取得に失敗しました:`, e);
                    break;
                }
            }
            // 月ごとに保存
            save(allData);
        }
    }

    logProgress(`\n✅ 全期間の取得が完了しました！合計: ${allData.length} 件 (新規追加: ${newCount} 件)`);

    // 集計報告
    const seaCount = allData.filter(d => d.category === 'sea').length;
    const freshCount = allData.filter(d => d.category === 'freshwater').length;
    const unknownCount = allData.filter(d => d.category === 'unknown').length;
    logProgress(`📊 内訳: 海 ${seaCount}, 淡水 ${freshCount}, 不明 ${unknownCount}`);
}

function save(data: JohshuyaFishingData[]) {
    // 日順ソート
    data.sort((a, b) => {
        const dateA = new Date(a.date.replace(/\//g, '-')).getTime();
        const dateB = new Date(b.date.replace(/\//g, '-')).getTime();
        return dateB - dateA;
    });
    fs.writeFileSync(SAVE_PATH, JSON.stringify(data, null, 2), 'utf-8');
}

main().catch(console.error);
