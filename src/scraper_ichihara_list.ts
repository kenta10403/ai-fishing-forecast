import * as cheerio from 'cheerio';

const LIST_URL_BASE = 'https://ichihara-umizuri.com/fishing/page/';

/**
 * ページネーションを順に巡回して、個別釣果記事のURLをすべて収集する
 * @param startPage 収集開始ページ
 * @param endPage 収集終了ページ (指定がない場合はリンクがなくなるまで)
 */
export async function scrapeIchiharaLinks(startPage = 1, endPage = 999): Promise<string[]> {
    const allLinks: Set<string> = new Set();

    for (let page = startPage; page <= endPage; page++) {
        const url = page === 1 ? 'https://ichihara-umizuri.com/fishing/' : `${LIST_URL_BASE}${page}/`;
        console.log(`Fetching list page: ${url}`);

        try {
            const res = await fetch(url);
            if (!res.ok) {
                if (res.status === 404) {
                    console.log(`Reached end of pagination at page ${page}.`);
                    break;
                }
                throw new Error(`HTTP Error: ${res.status}`);
            }

            const html = await res.text();
            const $ = cheerio.load(html);

            let linkFoundOnPage = false;
            $('a').each((i, el) => {
                const href = $(el).attr('href');
                if (href && href.match(/^https:\/\/ichihara-umizuri\.com\/fishing\/\d+\/?$/)) {
                    // ID「58」などは固定リンクやページネーション由来なので除外（記事IDは通常5桁以上）
                    const idMatch = href.match(/fishing\/(\d+)\/?$/);
                    if (idMatch && parseInt(idMatch[1], 10) > 100) {
                        allLinks.add(href);
                        linkFoundOnPage = true;
                    }
                }
            });

            // そのページに詳細へのリンクが1つもなければ最終ページと判断
            if (!linkFoundOnPage) {
                console.log(`No more articles found at page ${page}. Stopping pagination.`);
                break;
            }

            // サーバー負荷軽減のため少し待つ
            await new Promise(resolve => setTimeout(resolve, 300));

        } catch (e) {
            console.error(`Failed to fetch ${url}`, e);
            break;
        }
    }

    return Array.from(allLinks);
}

// テスト実行
if (require.main === module) {
    scrapeIchiharaLinks(1, 3).then(links => {
        console.log(`Found ${links.length} links from first 3 pages.`);
        console.log(links.slice(0, 5));
    }).catch(console.error);
}
