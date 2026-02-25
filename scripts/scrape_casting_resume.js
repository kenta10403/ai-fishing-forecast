const axios = require('axios');
const cheerio = require('cheerio');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'https://castingnet.jp/choka/search.php';
const OUTPUT_FILE = '/home/kenta/workspace/ai-fishing-forecast/data/casting_choka_full.json';
const DELAY_MS = 1000;

const KEYWORDS = {
    sea: ["アジ", "メバル", "カサゴ", "シーバス", "ヒラメ", "マダイ", "クロダイ", "チヌ", "ブリ", "ワラサ", "イナダ", "カンパチ", "ショゴ", "タチウオ", "アオリイカ", "コウイカ", "キス", "カワハギ", "アイナメ", "ソイ", "ハタ", "サバ", "イワシ", "サヨリ", "サワラ", "マダラ", "アマダイ", "メジナ", "グレ", "アカカマス", "サンノジ"],
    freshwater: ["ブラックバス", "バス", "トラウト", "ニジマス", "ヤマメ", "イワナ", "ワカサギ", "ヘラブナ", "フナ", "コイ", "ナマズ", "アゆ", "鮎"]
};

function getCategory(catches, field) {
    const text = (catches.map(c => c.name).join(' ') + ' ' + (field || '')).toLowerCase();
    for (const fish of KEYWORDS.freshwater) { if (text.indexOf(fish) !== -1) return 'freshwater'; }
    for (const fish of KEYWORDS.sea) { if (text.indexOf(fish) !== -1) return 'sea'; }
    if (field) {
        const fwFlags = ["池", "湖", "川", "管理釣り場"];
        const seaFlags = ["港", "浜", "磯", "堤防", "沖"];
        if (fwFlags.some(f => field.includes(f))) return 'freshwater';
        if (seaFlags.some(f => field.includes(f))) return 'sea';
    }
    return 'unknown';
}

async function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function fetchPage(year, month, page) {
    const url = `${BASE_URL}?choko_ys=${year}&choko_ms=${month}&page=${page}`;
    try {
        const response = await axios.get(url, {
            headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36' },
            timeout: 15000
        });
        return response.data;
    } catch (error) {
        console.error(`Error ${year}/${month} page ${page}: ${error.message}`);
        return null;
    }
}

function parsePage(html) {
    const $ = cheerio.load(html);
    const results = [];
    $('.result_detail').each((i, element) => {
        const item = { date: "", facility: "casting", catches: [], weather: "", waterTemp: "", category: "unknown", shopName: "", area: "", place: "" };
        let dateRaw = $(element).find('.day').text().trim();
        let dateStr = dateRaw.split('(')[0].replace(/年|月/g, '/').replace(/日/g, '');
        let parts = dateStr.split('/');
        if (parts.length === 3) {
            item.date = `${parts[0]}/${parts[1].padStart(2, '0')}/${parts[2].padStart(2, '0')}`;
        } else { item.date = dateRaw; }
        $(element).find('.result_table tr').each((j, tr) => {
            const name = $(tr).find('th').text().trim();
            const size = $(tr).find('td').text().trim().replace(/\s+/g, ' ');
            if (name) item.catches.push({ name, size, count: null });
        });
        $(element).find('.location_table tr').each((j, tr) => {
            const label = $(tr).find('th').text().trim();
            const value = $(tr).find('td').text().trim().replace(/\s+/g, ' ');
            if (label.includes('釣り場')) item.place = value;
            if (label.includes('天気')) item.weather = value;
        });
        item.shopName = $(element).find('.shop_name').text().trim();
        item.area = $(element).find('.prefectures').text().trim();
        item.category = getCategory(item.catches, item.place);
        if (item.shopName || item.date || item.catches.length > 0) results.push(item);
    });
    return results;
}

async function scrape() {
    const RESUME_YEAR = 2018;
    const RESUME_MONTH = 1;
    const NEW_OUTPUT_FILE = '/home/kenta/workspace/ai-fishing-forecast/data/casting_choka_resume.json';

    let allResults = [];
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth() + 1;

    console.log(`Resuming from ${RESUME_YEAR}/${RESUME_MONTH}`);

    for (let y = RESUME_YEAR; y <= currentYear; y++) {
        for (let m = 1; m <= 12; m++) {
            if (y === RESUME_YEAR && m < RESUME_MONTH) continue;
            if (y === currentYear && m > currentMonth) break;

            console.log(`--- Scraping ${y}/${m} ---`);
            let p = 1;
            while (true) {
                const html = await fetchPage(y, m, p);
                if (!html) break;
                const pageResults = parsePage(html);
                if (pageResults.length === 0) break;

                allResults = allResults.concat(pageResults);
                console.log(`${y}/${m} Page ${p}: Found ${pageResults.length}. Total: ${allResults.length}`);

                if (html.indexOf(`page=${p + 1}`) === -1) break;

                p++;
                await sleep(500);
            }
            fs.writeFileSync(NEW_OUTPUT_FILE, JSON.stringify(allResults, null, 2));
            await sleep(DELAY_MS);
        }
    }

    console.log(`Scraping completed. New items: ${allResults.length}`);

    // マージ作業
    console.log('Merging with existing data...');
    const existingDataRaw = fs.readFileSync(OUTPUT_FILE, 'utf8');
    let existingData = JSON.parse(existingDataRaw);

    // 2018年1月以降のデータを既存から除外（重複防止のため）
    const thresholdDate = "2018/01/01";
    const filteredExisting = existingData.filter(item => {
        return item.date < thresholdDate;
    });

    const mergedData = filteredExisting.concat(allResults);

    // 日付順にソート（オプションやけど綺麗にしとくわ）
    mergedData.sort((a, b) => a.date.localeCompare(b.date));

    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(mergedData, null, 2));
    console.log(`Merged data saved to ${OUTPUT_FILE}. Total items: ${mergedData.length}`);
}

scrape();

