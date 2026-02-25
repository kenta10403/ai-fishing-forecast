import fetch from 'node-fetch';
import * as cheerio from 'cheerio';
import { FishingData } from './scraper';

const BASE_URL = 'https://www.johshuya.co.jp/information/';

export interface JohshuyaFishingData extends FishingData {
    category: 'sea' | 'freshwater' | 'unknown';
    shopName: string;
    area: string; // 都道府県
}

// 海/淡水のキーワード定義
const FRESHWATER_KEYWORDS = ['湖', '池', '川', '渓流', '管理釣り場', 'ポンド', 'ダム', 'フォレスト', '不忘', 'あづみ野', 'フィッシングエリア', 'フィッシングパーク', 'フィッシングフィールド', 'フィッシングランド', 'ウォーターパーク', 'オーパ', 'プール', '池', '沼'];
const FRESHWATER_FISH = ['ワカサギ', 'ブラックバス', 'トラウト', 'ヤマメ', 'イワナ', 'ニジマス', 'ヘラブナ', 'コイ', '鮎', 'アユ', 'アマゴ', 'サツキマス', 'ブラウントラウト', 'レインボートラウト', 'サクラマス', 'タナゴ'];

const SEA_KEYWORDS = ['海', '港', '堤防', '磯', '浜', '沖', '湾', 'フィッシングピアー', 'ボート', 'マリーナ', 'テトラ', 'サーフ', '周辺', '釣行', '横須賀', '三浦', '真鶴', '湘南', '西湘', '房総', '九十九里', '駿河湾'];
const SEA_FISH = ['アジ', 'イワシ', 'サバ', 'メバル', 'カサゴ', 'チヌ', 'クロダイ', '真鯛', 'タイ', 'タチウオ', 'シーバス', 'スズキ', 'イカ', 'アオリイカ', 'ヒラメ', 'マゴチ', '青物', 'ブリ', 'ワラサ', 'ハマチ', 'イナダ', 'ソイ', '根魚', 'カワハギ', 'キス', 'シロギス'];

/**
 * 釣り場名や魚種から海か淡水かを見分ける
 */
export function judgeCategory(place: string, catches: { name: string }[]): 'sea' | 'freshwater' | 'unknown' {
    const combinedText = (place + catches.map(c => c.name).join('')).toLowerCase();

    // 淡水の判定が優先（湖などは明確なため）
    if (FRESHWATER_KEYWORDS.some(k => place.includes(k)) || FRESHWATER_FISH.some(f => combinedText.includes(f))) {
        return 'freshwater';
    }

    if (SEA_KEYWORDS.some(k => place.includes(k)) || SEA_FISH.some(f => combinedText.includes(f))) {
        return 'sea';
    }

    return 'unknown';
}

/**
 * 上州屋の釣果一覧ページ（1ページ分）をパースする
 */
export async function scrapeJohshuyaPage(page = 1): Promise<JohshuyaFishingData[]> {
    const url = page === 1 ? BASE_URL : `${BASE_URL}search.php?page=${page}`;
    console.log(`Fetching Johshuya page: ${url}`);

    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
    const html = await res.text();
    const $ = cheerio.load(html);

    const results: JohshuyaFishingData[] = [];

    $('.info__body').each((i, el) => {
        const $el = $(el);

        // 日付
        // <p class="info__date_txt"><span>‘26 </span>02月24日</p>
        const yearSuffix = $el.find('.info__date_txt span').text().trim().replace("‘", ""); // "26"
        const monthDay = $el.find('.info__date_txt').text().replace($el.find('.info__date_txt span').text(), "").trim(); // "02月24日"
        const year = `20${yearSuffix}`;
        const dateMatch = monthDay.match(/(\d+)月(\d+)日/);
        const formattedDate = dateMatch ? `${year}/${dateMatch[1].padStart(2, '0')}/${dateMatch[2].padStart(2, '0')}` : '';

        // 店舗・地域
        // <span class="info__tag">神奈川県</span>横須賀中央店
        const area = $el.find('.info__tag').text().trim();
        const shopRaw = $el.find('.info__area').text().trim();
        const shopName = shopRaw.replace(area, "").replace("店舗情報", "").replace("店舗の釣り情報", "").trim();

        // 釣り場
        // <th>釣り場</th><td>横須賀海辺つり公園</td>
        let place = '';
        $el.find('.info__detail th').each((j, th) => {
            if ($(th).text().trim() === '釣り場') {
                place = $(th).next('td').text().trim();
            }
        });

        // 釣果（魚種）
        // <table class="info__table"> <tbody> <tr> <th>魚種</th> <td>サイズ</td> <td>数</td> </tr> </tbody> </table>
        const catches: any[] = [];
        $el.find('.info__table tbody tr').each((j, tr) => {
            const fishName = $(tr).find('th').text().trim();
            const size = $(tr).find('td').first().text().trim();
            const countStr = $(tr).find('td').last().text().trim();

            if (fishName && fishName !== '魚種') {
                catches.push({
                    name: fishName,
                    count: parseInt(countStr.replace(/[^0-9]/g, '')) || 0,
                    size: size || undefined
                });
            }
        });

        // 天気・水温（上州屋には詳細がない場合が多いが一応枠だけ）
        const weather = '';
        const waterTemp = '';

        const category = judgeCategory(place, catches);

        results.push({
            date: formattedDate,
            facility: 'johshuya',
            catches,
            weather,
            waterTemp,
            category,
            shopName,
            area,
            place
        });
    });

    return results;
}
