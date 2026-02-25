import { scrapeJohshuyaPage } from './scraper_johshuya';

async function test() {
    console.log('🧪 Testing Johshuya Scraper (Page 1)...');
    try {
        const data = await scrapeJohshuyaPage(1);
        console.log(`✅ Success! Found ${data.length} articles.`);

        data.forEach((d, i) => {
            console.log(`\n[${i + 1}] ${d.date} @ ${d.place} (${d.shopName})`);
            console.log(`    Category: ${d.category}`);
            console.log(`    Catches: ${d.catches.map(c => `${c.name}(${c.count})`).join(', ')}`);
        });
    } catch (e) {
        console.error('❌ Test Failed:', e);
    }
}

test();
