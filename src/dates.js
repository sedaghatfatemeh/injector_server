import { CalendarDate, CalendarDateTime, GregorianCalendar, PersianCalendar, toCalendar, today } from '@internationalized/date';

export const timeZone = 'Asia/Tehran';
export const persianCalendar = new PersianCalendar();
const gregorianCalendar = new GregorianCalendar();
const numericOptions = { timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };
const display = new Intl.DateTimeFormat('fa-IR-u-ca-persian', numericOptions);
const detailedDisplay = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { ...numericOptions, second: '2-digit' });
export const months = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];

export function asciiDigits(value) {
  return String(value).replace(/[۰-۹٠-٩]/g, digit => String(digit.charCodeAt(0) - (digit >= '۰' ? 0x6f0 : 0x660)));
}

export function persianDigits(value) { return String(value).replace(/\d/g, digit => '۰۱۲۳۴۵۶۷۸۹'[Number(digit)]); }

export function formatPersianDateTime(value, { seconds = false } = {}) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const parts = Object.fromEntries((seconds ? detailedDisplay : display).formatToParts(date).map(({ type, value }) => [type, value]));
  // Isolate the numeric sequence inside Persian sentences and RTL table cells.
  return `\u2066${parts.year}/${parts.month}/${parts.day} ${parts.hour}:${parts.minute}${seconds ? `:${parts.second}` : ''}\u2069`;
}

export function parsePersianDateTime(value) {
  const match = asciiDigits(value).trim().match(/^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$/);
  if (!match) throw new Error('تاریخ شمسی را مانند ۱۴۰۴/۰۱/۰۱ ۱۲:۳۰:۰۰ وارد کنید.');
  const [year, month, day, hour, minute, second] = match.slice(1).map(value => Number(value || 0));
  const date = new CalendarDateTime(persianCalendar, year, month, day, hour, minute, second);
  if ([date.year, date.month, date.day, date.hour, date.minute, date.second].some((value, index) => value !== [year, month, day, hour, minute, second][index])) {
    throw new Error('تاریخ یا ساعت معتبر نیست؛ تعداد روزهای ماه و سال کبیسه را بررسی کنید.');
  }
  return date;
}

export function persianToUtc(value) {
  if (!String(value).trim()) return '';
  const date = parsePersianDateTime(value);
  try {
    // Explicit Gregorian conversion also keeps strict timezone disambiguation
    // independent of the calendar implementation and browser's local timezone.
    return toCalendar(date, gregorianCalendar).toDate(timeZone, 'reject').toISOString();
  } catch {
    throw new Error('این ساعت در زمان تهران معتبر یا یکتا نیست؛ ساعت دیگری انتخاب کنید.');
  }
}

export function parsePersianRange(after, before) {
  const start = persianToUtc(after);
  const end = persianToUtc(before);
  if (start && end && Date.parse(start) > Date.parse(end)) throw new Error('زمان شروع باید پیش از زمان پایان باشد.');
  return { after: start, before: end };
}

export function currentPersianDate() { return toCalendar(today(timeZone), persianCalendar); }

export function pickerDate(value) {
  try { const date = parsePersianDateTime(value); return new CalendarDate(persianCalendar, date.year, date.month, date.day); }
  catch { return currentPersianDate(); }
}

export function selectedDateText(date, previous) {
  const time = asciiDigits(previous).trim().split(/[ T]/)[1] || '00:00:00';
  return persianDigits(`${String(date.year).padStart(4, '0')}/${String(date.month).padStart(2, '0')}/${String(date.day).padStart(2, '0')} ${time}`);
}
