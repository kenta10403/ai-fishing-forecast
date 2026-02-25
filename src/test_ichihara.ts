import * as cheerio from 'cheerio';
import * as fs from 'fs';

async function fetchIchihara() {
  const url = 'https://ichihara-umizuri.com/fishing/24570/';
  const res = await fetch(url);
  const html = await res.text();
  const $ = cheerio.load(html);

  // 天気などの情報を探す
  $('div, p, span').each((i, el) => {
    const text = $(el).text().trim().replace(/\s+/g, ' ');
    if (text.includes('天気') && text.length < 50) {
      console.log(`[EnvData] ${text}`);
      // 親や兄弟を表示
      const parentHtml = $(el).parent().html()?.substring(0, 200);
      console.log('  Parent HTML:', parentHtml);
    }
    if (text.includes('フッコ') && text.length < 50) {
      console.log(`[FishData] ${text}`);
    }
  });

  // 全体のテキストをざっくり見る
  const allText = $('body').text().replace(/\s+/g, ' ');
  fs.writeFileSync('ichihara_dump.txt', allText);
}

fetchIchihara().catch(console.error);
