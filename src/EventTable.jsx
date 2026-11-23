import React from 'react';
import { locale } from './locale.js';

export const labels = {
  overview: 'نمای کلی', devices: 'دستگاه‌ها', customers: 'مشتریان', events: 'رویدادها', releases: 'به‌روزرسانی‌ها',
  active: 'فعال', resolved: 'رفع‌شده', info: 'اطلاعات', online: 'متصل', offline: 'قطع ارتباط',
  available: 'در انتظار', downloading: 'در حال دریافت', downloaded: 'دریافت‌شده', installing: 'در حال نصب',
  succeeded: 'موفق', failed: 'ناموفق', rolled_back: 'بازگشت‌شده', published: 'منتشرشده', withdrawn: 'پس‌گرفته‌شده',
};

export function formatDate(value) {
  return value ? new Date(value).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' }) : '—';
}

export function Status({ value }) {
  return <span className={`live-status ${value==='active'||value==='failed'?'danger':value==='online'||value==='resolved'||value==='succeeded'?'good':''}`}>{labels[value]||value||'—'}</span>;
}

export function Empty({ text }) {
  return <div className="live-empty">{text}</div>;
}

export default function EventTable({ events }) {
  if (!events.length) return <Empty text="رویدادی برای نمایش وجود ندارد."/>;
  return <div className="live-table-wrap"><table className="live-table"><thead><tr><th>رویداد</th><th>دستگاه</th><th>مشتری</th><th>وضعیت گزارش‌شده</th><th>زمان وقوع</th><th>زمان دریافت</th></tr></thead><tbody>{events.map(event=><tr key={event.id}><td><b>{event.summary||event.code}</b><small dir="ltr">{event.code}</small></td><td dir="ltr">{event.device_serial}</td><td>{event.customer_name}</td><td><Status value={event.state}/></td><td>{formatDate(event.occurred_at)}</td><td>{formatDate(event.received_at)}{Math.abs(new Date(event.received_at)-new Date(event.occurred_at))>300000&&<small>دریافت با تأخیر</small>}</td></tr>)}</tbody></table></div>;
}
