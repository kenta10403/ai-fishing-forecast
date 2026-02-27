import * as fs from 'fs';
import * as path from 'path';

const SAVE_PATH = path.join(__dirname, '../data/johshuya_history.json');

function cleanData() {
    if (!fs.existsSync(SAVE_PATH)) {
        console.log('No data found at', SAVE_PATH);
        return;
    }

    const data = JSON.parse(fs.readFileSync(SAVE_PATH, 'utf-8'));
    let modified = 0;
    let countsOver10000 = 0;

    for (const record of data) {
        if (!record.catches) continue;
        for (const c of record.catches) {
            if (c.count >= 10000) {
                countsOver10000++;
                // 1万匹以上の異常値。ハイフンが抜けてくっついた数値（例：300999 -> 300-999）と推測
                // 文字列の半分、または最初の数桁を取得して下限値とする。
                // 面倒なパースを避けるため、ここでは便宜的に「最初の3桁」または「長さを半分にした前半」を下限とする
                const str = String(c.count);
                let fixedCount = 0;
                if (str.length === 6) {
                    // 300999 -> 300
                    fixedCount = parseInt(str.substring(0, 3), 10);
                } else if (str.length === 7) {
                    // 7001600 -> 700
                    fixedCount = parseInt(str.substring(0, 3), 10);
                } else if (str.length === 5) {
                    // 100500 -> 100
                    fixedCount = parseInt(str.substring(0, 3), 10);
                } else {
                    // よほど変な値なら0にするか、前半を取る
                    fixedCount = parseInt(str.substring(0, Math.floor(str.length / 2)), 10) || 0;
                }

                console.log(`Fixing count: ${c.count} -> ${fixedCount} (Name: ${c.name}, Date: ${record.date}, Shop: ${record.shopName})`);
                c.count = fixedCount;
                modified++;
            }
        }
    }

    if (modified > 0) {
        fs.writeFileSync(SAVE_PATH, JSON.stringify(data, null, 2), 'utf-8');
        console.log(`✅ Fixed ${modified} anomalies out of ${countsOver10000} over-10000 catches.`);
    } else {
        console.log('✅ No anomalies >= 10000 found.');
    }
}

cleanData();
