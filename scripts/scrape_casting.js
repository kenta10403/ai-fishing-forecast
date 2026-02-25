const axios = require('axios');
const cheerio = require('cheerio');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'https://castingnet.jp/choka/search.php';
const OUTPUT_FILE = '/home/kenta/workspace/ai-fishing-forecast/data/casting_choka.json';
const MAX_PAGES = 920; 
const CONCURRENCY = 3; 
const DELAY_MS = 1000; 

// キーワード
const KEYWORDS = {
  sea: ["アジ", "メバル", "カサゴ", "シーバス", "ヒラメ", "マダイ", "クロダイ", "チヌ", "ブリ", "ワラサ", "イナダ", "カンパチ", "ショゴ", "タチウオ", "アオリイカ", "コウイカ", "キス", "カワハギ", "アイナメ", "ソイ", "ハタ", "サバ", "イワシ", "サヨリ", "サワラ", "マダラ", "アマダイ", "メジナ", "グレ", "アカカマス", "サンノジ"],
  freshwater: ["ブラックバス", "バス", "トラウト", "ニジマス", "ヤマメ", "イワナ", "ワカサギ", "ヘラブナ", "フナ", "コイ", "ナマズ", "アゆ", "鮎"]
};

function getCategory(catches, field) {
    const text = (catches.map(c => c.name).join(' ') + ' ' + (field || '')).toLowerCase();
    
    for (const fish of KEYWORDS.freshwater) {
        if (text.indexOf(fish) !== -1) return 'freshwater';
    }
    for (const fish of KEYWORDS.sea) {
        if (text.indexOf(fish) !== -1) return 'sea';
    }
    
    if (field) {
        const fwFlags = ["池", "湖", "川", "管理釣り場"];
        const seaFlags = ["港", "浜", "磯", "堤防", "沖"];
        if (fwFlags.some(f => field.includes(f))) return 'freshwater';
        if (seaFlags.some(f => field.includes(f))) return 'sea';
    }
    
    return 'unknown';
}

async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchPage(page) {
    const url = `${BASE_URL}?page=${page}`;
    console.log(`Fetching page ${page}: ${url}`);
    try {
        const response = await axios.get(url, {
            headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36' },
            timeout: 15000
        });
        return response.data;
    } catch (error) {
        console.error(`Error fetching page ${page}: ${error.message}`);
        return null;
    }
}

function parsePage(html) {
    const $ = cheerio.load(html);
    const results = [];

    $('.result_detail').each((i, element) => {
        const item = {
            date: "",
            facility: "casting",
            catches: [],
            weather: "",
            waterTemp: "",
            category: "unknown",
            shopName: "",
            area: "",
            place: ""
        };
        
        let dateRaw = $(element).find('.day').text().trim();
        let dateStr = dateRaw.split('(')[0].replace(/年/g, '/').replace(/月/g, '/').replace(/日/g, '');
        let parts = dateStr.split('/');
        if (parts.length === 3) {
            item.date = `${parts[0]}/${parts[1].padStart(2, '0')}/${parts[2].padStart(2, '0')}`;
        } else {
            item.date = dateRaw;
        }
        
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

        if (item.shopName || item.date || item.catches.length > 0) {
            results.push(item);
        }
    });
    return results;
}

async function scrape() {
    let allResults = [];
    for (let page = 1; page <= MAX_PAGES; page += CONCURRENCY) {
        const promises = [];
        for (let i = 0; i < CONCURRENCY && (page + i) <= MAX_PAGES; i++) {
            promises.push(fetchPage(page + i));
            await sleep(500);
        }
        const htmls = await Promise.all(promises);
        htmls.forEach((html, index) => {
            if (html) {
                const pageResults = parsePage(html);
                allResults = allResults.concat(pageResults);
                console.log(`Page ${page + index}: Found ${pageResults.length} items. Total: ${allResults.length}`);
            }
        });
        if (page % 30 === 1) fs.writeFileSync(OUTPUT_FILE, JSON.stringify(allResults, null, 2));
        await sleep(DELAY_MS);
    }
    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(allResults, null, 2));
    console.log(`Scraping completed. Total items: ${allResults.length}`);
}

if (process.argv.includes('--limit')) {
    (async () => {
        const html = await fetchPage(1);
        console.log(JSON.stringify(parsePage(html), null, 2));
    })();
} else {
    scrape();
}
