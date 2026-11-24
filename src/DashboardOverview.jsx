import React from 'react';
import { Activity, AlertTriangle, ArrowLeft, CloudDownload, Cpu, FileClock, Gauge, Monitor, Settings, ShieldCheck, Users, Wifi, WifiOff } from 'lucide-react';
import { Empty, formatDate, Status } from './EventTable.jsx';

const number = value => value == null ? '—' : new Intl.NumberFormat('fa-IR').format(value);

export function BrandMark() {
  return <span className="brand-mark" aria-hidden="true"><Settings/><Gauge/></span>;
}

export function StaffMasthead({ isAdmin }) {
  return <div className="dashboard-masthead"><div><b>پیشگامان شرق</b><span>سامانه مدیریت و پایش دستگاه‌های تست انژکتور</span></div><div className="dashboard-identity"><ShieldCheck size={23}/><span>{isAdmin ? 'مدیر سیستم' : 'پشتیبان'}</span></div></div>;
}

function InjectorArtwork() {
  return <svg className="injector-art" viewBox="0 0 430 170" fill="none" aria-hidden="true">
    <defs>
      <linearGradient id="injector-metal" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#262b32"/><stop offset=".22" stopColor="#e3e6e9"/><stop offset=".36" stopColor="#707c88"/><stop offset=".52" stopColor="#1d2229"/><stop offset=".75" stopColor="#b6c0c9"/><stop offset="1" stopColor="#20252c"/></linearGradient>
      <linearGradient id="injector-tip"><stop stopColor="#7a6a42"/><stop offset=".5" stopColor="#e5c077"/><stop offset="1" stopColor="#69512b"/></linearGradient>
    </defs>
    <g stroke="#83909e" opacity=".14"><path d="M260 0v170m40-170v170m40-170v170m40-170v170M220 40h210M220 80h210M220 120h210"/><circle cx="320" cy="80" r="57"/><circle cx="320" cy="80" r="45"/></g>
    <g transform="translate(27 23) rotate(17 190 65)" stroke="#0a0d12" strokeWidth="2">
      <path d="M23 41h37v55H23z" fill="url(#injector-metal)"/><rect x="45" y="29" width="56" height="79" rx="12" fill="url(#injector-metal)"/>
      <path d="M60 29V12h21v19" fill="#2b313a"/><rect x="90" y="35" width="97" height="66" rx="10" fill="url(#injector-metal)"/>
      <rect x="111" y="31" width="13" height="74" rx="3" fill="url(#injector-metal)"/><rect x="160" y="32" width="14" height="72" rx="3" fill="url(#injector-metal)"/>
      <path d="M187 43h43l27 10v31l-27 10h-43z" fill="url(#injector-metal)"/><path d="M255 54h53l27 9v12l-27 8h-53z" fill="url(#injector-metal)"/>
      <path d="m335 64 33 3v6l-33 2z" fill="url(#injector-tip)"/><path d="M369 69h15" stroke="#d6b776"/>
      <path d="M67 38v60m11-60v60M197 49v37m12-37v37m12-37v37M266 58v20m12-20v20m12-20v20" stroke="#e3eaf0" opacity=".3"/>
    </g>
  </svg>;
}

export default function DashboardOverview({ summary, devices, busy, isAdmin, onDevice, onNavigate }) {
  const metrics = [
    [Cpu, 'کل دستگاه‌ها', summary?.device_count, 'neutral'],
    [Wifi, 'متصل', summary?.online_count, 'green'],
    [WifiOff, 'قطع ارتباط', summary?.offline_count, 'red'],
    [AlertTriangle, 'خطاهای فعال', summary?.active_fault_count, 'orange'],
    [FileClock, 'رویدادهای ۲۴ ساعت', summary?.event_count_24h, 'blue'],
  ];
  const total = summary?.device_count || 0;
  const online = summary?.online_count || 0;
  const offline = summary?.offline_count || 0;
  return <div className="dashboard-overview" aria-busy={busy}>
    <section className="live-metrics" aria-label="آمار ناوگان">{metrics.map(([Icon, title, value, tone]) =>
      <article className={`metric-${tone}`} key={title}><Icon/><span>{title}</span><b>{number(value)}</b></article>)}</section>
    <section className="fleet-banner" aria-label="سامانه مدیریت و پایش"><div className="banner-brand"><BrandMark/><b>پیشگامان شرق</b></div><div className="banner-copy"><h2>سامانه مدیریت و پایش</h2><p>دستگاه‌های تست انژکتور و یونیت دیزل</p><i/></div><InjectorArtwork/></section>
    <div className="overview-panels">
      <section className="live-card latest-devices"><div className="overview-card-heading"><h2><Monitor size={19}/> آخرین دستگاه‌ها</h2><button onClick={() => onNavigate('devices')}>مشاهده همه <ArrowLeft size={14}/></button></div>
        {!devices.length ? <Empty text={busy ? 'در حال دریافت دستگاه‌ها…' : 'هنوز دستگاهی ثبت نشده است.'}/> : <div className="live-table-wrap"><table className="live-table"><thead><tr><th>شناسه دستگاه</th><th>وضعیت تخمینی</th><th>آخرین ارتباط</th><th>محل نصب</th></tr></thead><tbody>{devices.slice(0, 5).map(device => <tr key={device.id}><td><button dir="ltr" onClick={() => onDevice(device)}><Monitor size={14}/>{device.serial_number}</button></td><td><Status value={device.is_online ? 'online' : 'offline'}/></td><td>{device.last_seen_at ? formatDate(device.last_seen_at) : 'هنوز متصل نشده'}</td><td>{device.installation_location || '—'}</td></tr>)}</tbody></table></div>}
      </section>
      <section className="live-card fleet-connectivity"><div className="overview-card-heading"><h2><Activity size={19}/> وضعیت ارتباط ناوگان</h2><span>بر اساس آخرین ارتباط</span></div>
        <div className="fleet-chart" role="img" aria-label={summary ? `${number(online)} متصل و ${number(offline)} بدون ارتباط اخیر از ${number(total)} دستگاه` : 'آمار اتصال هنوز دریافت نشده است'}><div className="fleet-donut" style={{ '--online-share': `${total ? online / total * 100 : 0}%`, '--offline-ring': total ? '#e9bbc3' : 'var(--live-border)' }}><div><b>{summary ? number(total) : '—'}</b><span>دستگاه</span></div></div><div className="fleet-legend"><p><i className="legend-online"/> ارتباط اخیر <b>{summary ? number(online) : '—'}</b></p><p><i className="legend-offline"/> بدون ارتباط اخیر <b>{summary ? number(offline) : '—'}</b></p></div></div>
        <p className="connection-note">تخمین اتصال با آستانهٔ {number(summary?.online_window_minutes ?? 15)} دقیقه؛ مشاهدهٔ وضعیت، ارتباطی با دستگاه برقرار نمی‌کند.</p>
      </section>
    </div>
    <section className="dashboard-shortcuts" aria-label="دسترسی سریع">{[
      ['events', 'رویدادها و خطاها', 'بررسی گزارش‌ها و وضعیت خطاها', Monitor, 'green'],
      ['devices', 'مدیریت دستگاه‌ها', 'مشخصات و آخرین ارتباط دستگاه‌ها', Cpu, 'orange'],
      ['releases', 'به‌روزرسانی نرم‌افزار', 'نسخه‌ها و نتایج گزارش‌شده', CloudDownload, 'blue'],
      [isAdmin ? 'users' : 'customers', isAdmin ? 'مدیریت کاربران' : 'مشتریان', isAdmin ? 'تعریف دسترسی و حساب‌ها' : 'اطلاعات سازمان‌ها و مشتریان', Users, 'purple'],
    ].map(([page, title, subtitle, Icon, tone]) => <button key={page} className={`shortcut-${tone}`} onClick={() => onNavigate(page)}><Icon/><span><b>{title}</b><small>{subtitle}</small></span><ArrowLeft className="shortcut-arrow" size={15}/></button>)}</section>
  </div>;
}
