import React from 'react';
import { formatPersianDateTime } from './dates.js';
import './record-history.css';

function Stamp({ entry, fallback, unknown = false }) {
  const date = entry?.at || fallback;
  if (!date) return <span className="record-history-unknown">{unknown ? 'نامشخص' : 'ثبت نشده'}</span>;
  return <><time dateTime={date}>{formatPersianDateTime(date, { seconds: true })}</time><small>{entry?.by || 'عامل نامشخص'}</small></>;
}

export function RecordHistoryHeaders({ archive = false, withdrawal = false }) {
  return <><th>تاریخ ایجاد</th><th>آخرین ویرایش مدیریتی</th>{archive && <th>آخرین بایگانی و انجام‌دهنده</th>}{withdrawal && <th>پس‌گرفتن و انجام‌دهنده</th>}</>;
}

export function RecordHistoryCells({ record, archive = false, withdrawal = false }) {
  const history = record.record_history;
  return <><td className="record-history-cell"><Stamp entry={history?.created} fallback={record.created_at || record.date_joined}/></td><td className="record-history-cell"><Stamp entry={history?.edited}/></td>{archive && <td className="record-history-cell">{history?.archived || record.is_archived ? <Stamp entry={history?.archived} unknown/> : '—'}</td>}{withdrawal && <td className="record-history-cell">{history?.withdrawn || record.status === 'withdrawn' ? <Stamp entry={history?.withdrawn} unknown/> : '—'}</td>}</>;
}

export default function RecordHistory({ record, archive = false }) {
  const history = record.record_history;
  return <section className="record-history-detail" aria-label="سوابق ثبت رکورد"><h3>سوابق ثبت رکورد · ساعت تهران</h3><dl><dt>تاریخ ایجاد</dt><dd><Stamp entry={history?.created} fallback={record.created_at || record.date_joined}/></dd><dt>آخرین ویرایش مدیریتی</dt><dd><Stamp entry={history?.edited}/></dd>{archive && <><dt>آخرین بایگانی</dt><dd>{history?.archived || record.is_archived ? <Stamp entry={history?.archived} unknown/> : '—'}</dd></>}</dl></section>;
}
