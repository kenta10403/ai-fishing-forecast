import * as cheerio from 'cheerio';

async function fetchList() {
    const url = 'https://ichihara-umizuri.com/fishing/';
    const res = await fetch(url);
    const html = await res.text();
    const $ = cheerio.load(html);

    const links = new Set<string>();
    $('a').each((i, el) => {
        const href = $(el).attr('href');
        if (href && href.match(/https:\/\/ichihara-umizuri.com\/fishing\/\d+\/$/)) {
            links.add(href);
        }
    });

    console.log('--- Detail Links ---');
    Array.from(links).forEach(l => console.log(l));

    const pages = new Set<string>();
    $('a').each((i, el) => {
        const href = $(el).attr('href');
        if (href && href.match(/https:\/\/ichihara-umizuri.com\/fishing\/page\/\d+\/$/)) {
            pages.add(href);
        }
    });
    console.log('--- Pagination Links ---');
    Array.from(pages).forEach(l => console.log(l));
}

fetchList().catch(console.error);
