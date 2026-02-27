import { test } from 'node:test';
import * as assert from 'node:assert';

function parseCount(countStr: string): number {
    let count = 0;
    if (countStr.includes('-')) {
        const minStr = countStr.split('-')[0];
        count = parseInt(minStr.replace(/[^0-9]/g, ''), 10) || 0;
    } else if (countStr.includes('～')) { // 全角波ダッシュ
        const minStr = countStr.split('～')[0];
        count = parseInt(minStr.replace(/[^0-9]/g, ''), 10) || 0;
    } else if (countStr.includes('~')) { // 半角チルダ
        const minStr = countStr.split('~')[0];
        count = parseInt(minStr.replace(/[^0-9]/g, ''), 10) || 0;
    } else {
        count = parseInt(countStr.replace(/[^0-9]/g, ''), 10) || 0;
    }
    return count;
}

test('parseCount correctly parses range string', () => {
    assert.strictEqual(parseCount('300-999匹'), 300);
    assert.strictEqual(parseCount('300-999'), 300);
    assert.strictEqual(parseCount('10-20'), 10);
    assert.strictEqual(parseCount('10～20匹'), 10);
    assert.strictEqual(parseCount('5~10'), 5);
    assert.strictEqual(parseCount('100匹'), 100);
    assert.strictEqual(parseCount('匹'), 0);
    assert.strictEqual(parseCount(' - '), 0);
});
