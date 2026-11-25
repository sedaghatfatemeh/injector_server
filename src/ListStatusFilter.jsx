import React from 'react';

export default function ListStatusFilter({ value, onChange, kind = 'archive', label }) {
  const variants = {
    archive: [['active', 'فعال'], ['archived', 'بایگانی‌شده'], ['all', 'همه']],
    account: [['', 'همه'], ['true', 'فعال'], ['false', 'غیرفعال']],
    release: [['', 'همه'], ['published', 'منتشرشده'], ['withdrawn', 'پس‌گرفته‌شده'], ['draft', 'پیش‌نویس']],
  };
  const title = label || (kind === 'archive' ? 'وضعیت بایگانی' : kind === 'release' ? 'وضعیت نسخه' : 'وضعیت حساب');
  return <div className="live-filter"><label><span>{title}</span><select aria-label={title} value={value} onChange={event => onChange(event.target.value)}>{variants[kind].map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label></div>;
}

export function ListPagination({ payload, page, onPage, loading }) {
  return <nav className="live-staff-pagination" aria-label="صفحه‌بندی فهرست"><button className="live-secondary" disabled={loading || !payload?.previous} onClick={() => onPage(page - 1)}>قبلی</button><span>صفحهٔ {page.toLocaleString('fa-IR')} · {payload && !loading ? Number(payload.count ?? 0).toLocaleString('fa-IR') : '—'} مورد</span><button className="live-secondary" disabled={loading || !payload?.next} onClick={() => onPage(page + 1)}>بعدی</button></nav>;
}
