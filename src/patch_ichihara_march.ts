import * as fs from 'fs';
import * as path from 'path';
import { scrapeIchiharaDetail } from './scraper_ichihara_detail';
import { FishingData } from './scraper';

const SAVE_PATH = path.join(__dirname, '../data/ichihara_2024_to_present.json');

// 遅延実行用のヘルパー関数
const delay = (ms: number) => new Promise(res => setTimeout(res, ms));

async function main() {
    console.log('🔍 2024年3月分のデータ補完（IDスキャン）を開始します...');

    let allData: FishingData[] = [];
    if (fs.existsSync(SAVE_PATH)) {
        try {
            const raw = fs.readFileSync(SAVE_PATH, 'utf-8');
            const json = JSON.parse(raw);
            allData = json.data || [];
        } catch (e) {
            console.error('既存データの読み込みに失敗しました。');
            return;
        }
    }

    const existingDates = new Set(allData.map(d => d.date));

    // 3月分は ID 60〜70 付近にあることが推測されるため、広めにスキャン
    // 3/31 が ID 58 よりも少し大きい ID になっている可能性がある
    // ID 62 が 3/3 なら、3/1 は 64〜65 付近？ 
    // 安全のため 50〜150 くらいまでスキャンしてみる
    const startId = 50;
    const endId = 150;

    console.log(`スキャン範囲: ID ${startId} 〜 ${endId}`);

    for (let id = startId; id <= endId; id++) {
        const url = `https://ichihara-umizuri.com/fishing/${id}/`;

        try {
            const data = await scrapeIchiharaDetail(url);
            if (data) {
                if (data.date.startsWith('2024/03/')) {
                    if (!existingDates.has(data.date)) {
                        console.log(`✅ Found 3月データ: ${data.date} (ID: ${id})`);
                        allData.push(data);
                        existingDates.add(data.date);
                    } else {
                        console.log(`⏩ Already exists: ${data.date} (ID: ${id})`);
                    }
                } else {
                    // 3月以外でも2024年で未取得なら一応入れる
                    if (data.date.startsWith('2024/') && !existingDates.has(data.date)) {
                        console.log(`✅ Found 2024データ: ${data.date} (ID: ${id})`);
                        allData.push(data);
                        existingDates.add(data.date);
                    }
                }
            }
        } catch (e) {
            // スキップ
        }
        await delay(200);
    }

    // 保存
    allData.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

    // メタデータも更新
    const output = {
        metadata: {
            last_fetched_date: allData.length > 0 ? allData[0].date : '2024/04/01',
            facility: 'ichihara',
            updated_at: new Date().toISOString(),
            note: 'Manual patch for 2024/03'
        },
        data: allData
    };

    fs.writeFileSync(SAVE_PATH, JSON.stringify(output, null, 2), 'utf-8');
    console.log(`\n🎉 補完完了！合計: ${allData.length} 件`);
}

main().catch(console.error);
