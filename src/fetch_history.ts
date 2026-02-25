import * as fs from 'fs';
import * as path from 'path';

import 'dotenv/config';

const API_URL = process.env.APPSYNC_API_URL || '';
const API_KEY = process.env.APPSYNC_API_KEY || '';

interface FishCatch {
    name: string;
    count: number;
    size?: string;
    place?: string;
}

interface FishingData {
    date: string;
    facility: string;
    weather: string;
    waterTemp: string;
    tide: string;
    visitors: number | string;
    sentence: string;
    catches: FishCatch[];
}

interface FacilityJsonFormat {
    metadata: {
        last_fetched_date: string;
        facility: string;
        updated_at: string;
    };
    data: FishingData[];
}

export async function fetchFishingData(facility: string, targetDate: string): Promise<FishingData | null> {
    const fishFields = Array.from({ length: 30 }, (_, i) => i + 1).map(i => `
      fish${i}Name
      fish${i}MinSize
      fish${i}MaxSize
      fish${i}Count
      fish${i}Place
  `).join('');

    const query = `
    query LastPostsByFacilityAndDate($facility: String!, $date: ModelStringKeyConditionInput) {
      lastPostsByFacilityAndDate(facility: $facility, date: $date) {
        items {
          date
          facility
          sentence
          weather
          waterTemp
          tide
          visitors
          ${fishFields}
        }
      }
    }
  `;

    const variables = {
        facility,
        date: { eq: targetDate }
    };

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': API_KEY,
            },
            body: JSON.stringify({ query, variables })
        });

        if (!response.ok) {
            console.error(`[Error] HTTP Status: ${response.status} on ${targetDate}`);
            return null;
        }

        const json = await response.json();
        const items = json.data?.lastPostsByFacilityAndDate?.items;

        if (!items || items.length === 0) {
            return null;
        }

        const rawData = items[0];
        const catches: FishCatch[] = [];

        for (let i = 1; i <= 30; i++) {
            const name = rawData[`fish${i}Name`];
            const countStr = rawData[`fish${i}Count`];

            if (name && countStr) {
                const minSize = rawData[`fish${i}MinSize`];
                const maxSize = rawData[`fish${i}MaxSize`];
                let sizeStr = undefined;

                if (minSize && maxSize && minSize !== maxSize) {
                    sizeStr = `${minSize}～${maxSize}cm`;
                } else if (maxSize) {
                    sizeStr = `${maxSize}cm`;
                }

                catches.push({
                    name,
                    count: parseInt(countStr, 10) || 0,
                    size: sizeStr,
                    place: rawData[`fish${i}Place`] || undefined,
                });
            }
        }

        return {
            date: rawData.date,
            facility: rawData.facility,
            weather: rawData.weather,
            waterTemp: rawData.waterTemp,
            tide: rawData.tide,
            visitors: rawData.visitors,
            sentence: rawData.sentence,
            catches,
        };
    } catch (error) {
        console.error(`[Exception] Failed to fetch data for ${targetDate}:`, error);
        return null;
    }
}

function formatDate(date: Date): string {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}/${m}/${d}`;
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
    const facilities = ['honmoku', 'daikoku', 'isogo'];
    const outputDir = path.join(__dirname, '../data');

    if (!fs.existsSync(outputDir)) {
        fs.mkdirSync(outputDir, { recursive: true });
    }

    for (const facility of facilities) {
        console.log(`\n🚀 取得・更新開始: ${facility}`);

        const outputFile = path.join(outputDir, `${facility}_2024_to_present.json`);
        let allData: FishingData[] = [];
        let lastDate = '2024/01/01';

        // 既存データの読み込みと形式変換
        if (fs.existsSync(outputFile)) {
            try {
                const raw = fs.readFileSync(outputFile, 'utf-8');
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed)) {
                    // 旧フォーマット
                    allData = parsed;
                } else if (parsed && parsed.data) {
                    // 新フォーマット
                    allData = parsed.data;
                    lastDate = parsed.metadata.last_fetched_date;
                }
                console.log(`📜 既存データを確認: ${allData.length} 件 (最新: ${lastDate})`);
            } catch (e) {
                console.warn('⚠️ 既存データのパースに失敗しました。');
            }
        }

        const existingDates = new Set(allData.map(d => d.date));

        // 収集期間: lastDate の翌日から 昨日まで
        const startDate = new Date(lastDate);
        startDate.setDate(startDate.getDate() + 1);

        const endDate = new Date();
        endDate.setDate(endDate.getDate() - 1);

        if (startDate > endDate) {
            console.log('✅ データは既に最新です。');
            continue;
        }

        console.log(`⏳ ${formatDate(startDate)} 〜 ${formatDate(endDate)} の差分を取得します...`);

        let currentDate = new Date(startDate);
        let successCount = 0;

        while (currentDate <= endDate) {
            const targetDateStr = formatDate(currentDate);

            if (!existingDates.has(targetDateStr)) {
                process.stdout.write(`Fetching ${targetDateStr}... `);
                const data = await fetchFishingData(facility, targetDateStr);

                if (data) {
                    allData.push(data);
                    successCount++;
                    process.stdout.write(`✅ Success (${data.catches.length} catches)\n`);
                } else {
                    process.stdout.write(`➖ No data\n`);
                }
                await sleep(100);
            }
            currentDate.setDate(currentDate.getDate() + 1);
        }

        // ソートと保存
        allData.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
        const newLastDate = allData.length > 0 ? allData[0].date : lastDate;

        const output: FacilityJsonFormat = {
            metadata: {
                last_fetched_date: newLastDate,
                facility: facility,
                updated_at: new Date().toISOString()
            },
            data: allData
        };

        fs.writeFileSync(outputFile, JSON.stringify(output, null, 2), 'utf-8');

        console.log('\n=======================================');
        console.log(`🎉 完了: ${facility}`);
        console.log(`📊 新規追加: ${successCount} 日`);
        console.log(`📁 保存先: ${outputFile}`);
        console.log(`📈 最新日付: ${newLastDate} (合計: ${allData.length} 件)`);
        console.log('=======================================\n');
    }
}

if (require.main === module) {
    main().catch(console.error);
}
