const API_URL = 'https://iqqdsybr6beovaix6btxwykuha.appsync-api.ap-northeast-1.amazonaws.com/graphql';
const API_KEY = 'da2-of4bzmdi4vhjha5buiog37mki4';

interface FishCatch {
    name: string;
    count: number;
    size?: string;
    place?: string;
}

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
    // 市原などの詳細な環境データ
    details?: {
        airTemp?: string;       // 気温 (15 / 3 ℃)
        windSpeed?: string;    // 風速 (3.0～5.0 m/s)
        windDir?: string;      // 風向き
        highTide?: string;     // 満潮
        lowTide?: string;      // 干潮
        warning?: string;      // 警報
        caution?: string;      // 注意報
    };
}

interface ScrapingMeta {
    last_fetched_date: string;
    facility: string;
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

    const response = await fetch(API_URL, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-api-key': API_KEY,
        },
        body: JSON.stringify({ query, variables })
    });

    if (!response.ok) {
        console.error(`HTTP Error: ${response.status}`);
        return null;
    }

    const json = await response.json();
    const items = json.data?.lastPostsByFacilityAndDate?.items;

    if (!items || items.length === 0) {
        console.log(`[Warning] No data found for ${facility} on ${targetDate}`);
        return null;
    }

    const rawData = items[0];

    // 釣果データを整形
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
}

async function main() {
    console.log('🐟 Fetching data from Yokohama Fishing Piers API...\n');

    // 昨日の日付を yyyy/mm/dd 形式で取得 (UTC+9)
    const d = new Date();
    d.setDate(d.getDate() - 1); // 昨日のデータを取得（最新の確定データ）
    const yestY = d.getFullYear();
    const yestM = String(d.getMonth() + 1).padStart(2, '0');
    const yestD = String(d.getDate()).padStart(2, '0');
    const yesterday = `${yestY}/${yestM}/${yestD}`;

    console.log(`[Target]: 本牧海づり施設 (${yesterday})`);
    const data = await fetchFishingData('honmoku', yesterday);

    if (data) {
        console.log('\n✅ データの取得・整形に成功しました！\n');
        console.log(JSON.stringify(data, null, 2));
    } else {
        // データがない場合は一昨日をパースしてみる
        d.setDate(d.getDate() - 1);
        const dayBeforeYest = `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`;
        console.log(`\n[Retry Target]: 本牧海づり施設 (${dayBeforeYest})`);
        const retryData = await fetchFishingData('honmoku', dayBeforeYest);
        if (retryData) {
            console.log('\n✅ データの取得・整形に成功しました！\n');
            console.log(JSON.stringify(retryData, null, 2));
        }
    }
}

// 実行エントリーポイント
if (require.main === module) {
    main().catch(console.error);
}
