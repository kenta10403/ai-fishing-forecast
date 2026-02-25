import * as cheerio from 'cheerio';
import { FishingData, FishCatch } from './scraper';

/**
 * 市原の個別の釣果ページからデータを抽出し、FishingData形式で返す
 * @param url 個別記事のURL
 */
export async function scrapeIchiharaDetail(url: string): Promise<FishingData | null> {
    try {
        const res = await fetch(url);
        if (!res.ok) {
            throw new Error(`HTTP Error: ${res.status}`);
        }
        const html = await res.text();
        const $ = cheerio.load(html);

        // 日付 (本文中の「2026年02月21日(土)」などを探す)
        let dateStr = '';
        $('p').each((i, el) => {
            const text = $(el).text().trim();
            const match = text.match(/^(\d{4})年(\d{2})月(\d{2})日/);
            if (match) {
                dateStr = `${match[1]}/${match[2]}/${match[3]}`;
            }
        });
        if (!dateStr) {
            // 見つからない場合は別の要素も探す
            const h1Text = $('h1').text().trim();
            const h1Match = h1Text.match(/(\d{4})年(\d{2})月(\d{2})日/);
            if (h1Match) {
                dateStr = `${h1Match[1]}/${h1Match[2]}/${h1Match[3]}`;
            }
        }

        if (!dateStr) {
            console.warn(`[scrapeIchiharaDetail] Could not find date for ${url}`);
            return null;
        }

        // 環境データ (詳細な抽出)
        let weather = '';
        let waterTemp = '';
        let tide = '';
        let visitors: string | number = 0;
        let sentence = '';

        // 天気情報の抽出 (<span>天気</span> の次の <span> にテキストがある)
        $('span').each((i, el) => {
            if ($(el).text().trim() === '天気') {
                weather = $(el).next('span').text().trim();
            }
        });
        // バックアップ: アイコン画像名
        if (!weather) {
            const weatherAlt = $('span > img[src*="wether"]').first().attr('alt');
            if (weatherAlt) weather = weatherAlt;
        }

        const details: NonNullable<FishingData['details']> = {};

        // 共通のテーブル構造 (.whitespace-nowrap) から抽出
        $('.whitespace-nowrap').each((i, el) => {
            const label = $(el).find('p').first().text().trim();
            const valueEl = $(el).find('p').last();
            let value = valueEl.text().trim().replace(/\s+/g, ' ');

            if (label === '気温') {
                details.airTemp = value;
            } else if (label === '水温') {
                waterTemp = value;
            } else if (label === '風向き') {
                details.windDir = value;
            } else if (label === '風速') {
                details.windSpeed = value;
            } else if (label === '潮') {
                tide = value;
            } else if (label === '満潮') {
                details.highTide = value;
            } else if (label === '干潮') {
                details.lowTide = value;
            } else if (label === '警報') {
                details.warning = value;
            } else if (label === '注意報') {
                details.caution = value;
            }
        });

        // 本文と来場者数
        const bodyTexts: string[] = [];
        $('.mt-12 p').each((i, el) => {
            const txt = $(el).text().trim();
            if (txt) {
                bodyTexts.push(txt);
                const visitorMatch = txt.match(/入場者数は(\d+)名/);
                if (visitorMatch) {
                    visitors = parseInt(visitorMatch[1], 10);
                }
            }
        });
        sentence = bodyTexts.join('\n');

        // 釣果データ
        const catches: FishCatch[] = [];
        $('.flex.border-b.border-gray-300').each((i, row) => {
            const cols = $(row).find('div');
            if (cols.length >= 3) {
                const fishName = $(cols[0]).text().trim();
                const sizeStr = $(cols[1]).text().trim().replace(/\s+/g, ' ');
                const countStr = $(cols[2]).text().trim();

                if (fishName && countStr && fishName !== '釣果' && !fishName.includes('桟橋')) {
                    let count = 0;
                    const countMatch = countStr.match(/(\d+)匹/);
                    if (countMatch) {
                        count = parseInt(countMatch[1], 10);
                    } else if (!isNaN(parseInt(countStr, 10))) {
                        count = parseInt(countStr, 10);
                    }

                    if (count > 0) {
                        catches.push({
                            name: fishName,
                            count: count,
                            size: sizeStr || undefined,
                            place: undefined
                        });
                    }
                }
            }
        });

        return {
            date: dateStr,
            facility: 'ichihara',
            catches,
            weather: weather || '不明',
            waterTemp: waterTemp || '不明',
            tide: tide || '不明',
            visitors,
            sentence,
            details
        };

    } catch (e) {
        console.error(`[scrapeIchiharaDetail] Failed. URL: ${url}`, e);
        return null;
    }
}

if (require.main === module) {
    scrapeIchiharaDetail('https://ichihara-umizuri.com/fishing/24570/').then(data => {
        console.log(JSON.stringify(data, null, 2));
    });
}
