import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { asciiDigits, formatPersianDateTime, parsePersianDateTime, parsePersianRange, persianToUtc } from '../../src/dates.js';

test('Persian and Arabic digits map to the same Tehran instant across Nowruz', () => {
  for (const input of ['1404/01/01 00:00:00', '۱۴۰۴/۰۱/۰۱ ۰۰:۰۰:۰۰', '١٤٠٤/٠١/٠١ ٠٠:٠٠:٠٠']) {
    assert.equal(persianToUtc(input), '2025-03-20T20:30:00.000Z');
  }
  assert.equal(persianToUtc('1399/12/30 23:59:59'), '2021-03-20T20:29:59.000Z');
  assert.equal(persianToUtc('1403/12/30'), '2025-03-19T20:30:00.000Z');
  assert.equal(parsePersianDateTime('1404/01/01 12:30:15').second, 15);
});

for (const value of ['1404/12/30', '1404/07/31', '1404/00/01', '1404/13/01', '1404/01/00', '0000/01/01', '9999/01/01', '1404/01/01 24:00', '1404/01/01 12:60', '1404/01/01 12:30:60', 'not-a-date']) {
  test(`invalid input is rejected rather than constrained: ${value}`, () => assert.throws(() => persianToUtc(value)));
}

test('historical Tehran DST gaps and repeated times require an unambiguous input', () => {
  assert.throws(() => persianToUtc('1400/01/02 00:30:00'), /معتبر یا یکتا نیست/);
  assert.throws(() => persianToUtc('1400/06/30 23:30:00'), /معتبر یا یکتا نیست/);
});

test('open, empty, equal and reversed ranges are handled explicitly', () => {
  assert.deepEqual(parsePersianRange('', ''), { after: '', before: '' });
  assert.equal(parsePersianRange('1404/01/01', '').before, '');
  assert.equal(parsePersianRange('', '1404/01/01').after, '');
  const same = parsePersianRange('1404/01/01', '1404/01/01');
  assert.equal(same.after, same.before);
  assert.throws(() => parsePersianRange('1404/01/02', '1404/01/01'), /زمان شروع/);
});

test('display uses Persian calendar and Tehran even across the UTC date boundary', () => {
  const formatted = asciiDigits(formatPersianDateTime('2025-03-20T20:30:00Z'));
  assert.equal(formatted, '\u20661404/01/01 00:00\u2069');
  assert.match(formatted, /00:00/);
  assert.equal(formatPersianDateTime(null), '—');
  assert.equal(formatPersianDateTime('invalid'), '—');
  assert.equal(asciiDigits(formatPersianDateTime('2025-03-20T20:30:03Z', { seconds: true })), '\u20661404/01/01 00:00:03\u2069');
});

test('conversion and display are independent of the process timezone', () => {
  const script = "import {persianToUtc,formatPersianDateTime} from './src/dates.js'; console.log(JSON.stringify([persianToUtc('1404/01/01'),formatPersianDateTime('2025-03-20T20:30:00Z')]));";
  const results = ['UTC', 'America/Los_Angeles', 'Asia/Tehran'].map(TZ => {
    const result = spawnSync(process.execPath, ['--input-type=module', '-e', script], { env: { ...process.env, TZ }, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    return result.stdout;
  });
  assert.equal(new Set(results).size, 1);
});
