import React, { useEffect, useState } from 'react';
import { api } from './api.js';
import EventTable from './EventTable.jsx';

const emptyFilters = { search: '', serial: '', customer: '', state: '', after: '', before: '', archivedDevices: false, archivedCustomers: false };

export default function EventHistory({ refreshKey = 0, onSessionExpired }) {
  const [draft, setDraft] = useState(emptyFilters);
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [validation, setValidation] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError('');
    const params = { page };
    if (filters.search) params.search = filters.search;
    if (filters.serial) params.device__serial_number__icontains = filters.serial;
    if (filters.customer) params.device__customer__organization_name__icontains = filters.customer;
    if (filters.state) params.state = filters.state;
    if (filters.after) params.occurred_after = new Date(filters.after).toISOString();
    if (filters.before) params.occurred_before = new Date(filters.before).toISOString();
    if (filters.archivedDevices) params.device__is_archived = 'true';
    if (filters.archivedCustomers) params.device__customer__is_archived = 'true';
    api.events(params, { signal: controller.signal }).then(payload => {
      if (!controller.signal.aborted) setResult(payload);
    }).catch(cause => {
      if (!controller.signal.aborted) {
        if (cause.status === 401 || cause.status === 403) onSessionExpired?.();
        setResult(null);
        setError(cause.message || 'دریافت رویدادها انجام نشد.');
      }
    }).finally(() => {
      if (!controller.signal.aborted) setBusy(false);
    });
    return () => controller.abort();
  }, [filters, page, revision, refreshKey, onSessionExpired]);

  function apply(event) {
    event.preventDefault();
    if (draft.after && draft.before && new Date(draft.after) > new Date(draft.before)) {
      setValidation('زمان شروع باید پیش از زمان پایان باشد.');
      return;
    }
    setValidation('');
    setPage(1);
    setFilters(Object.fromEntries(Object.entries(draft).map(([key, value]) => [key, value.trim()])));
  }

  function reset() {
    setDraft(emptyFilters);
    setFilters(emptyFilters);
    setPage(1);
    setValidation('');
    setRevision(value => value + 1);
  }

  const field = (key) => ({ value: draft[key], onChange: event => setDraft(value => ({ ...value, [key]: event.target.value })) });
  return <section className="live-card" aria-label="تاریخچه رویدادها">
    <form className="live-event-filters" onSubmit={apply}>
      <label className="live-field"><span>جست‌وجوی کد یا خلاصه</span><input type="search" {...field('search')}/></label>
      <label className="live-field"><span>سریال دستگاه</span><input dir="ltr" {...field('serial')}/></label>
      <label className="live-field"><span>نام مشتری</span><input {...field('customer')}/></label>
      <label className="live-field"><span>وضعیت گزارش‌شده</span><select {...field('state')}><option value="">همه</option><option value="active">فعال</option><option value="resolved">رفع‌شده</option><option value="info">اطلاعات</option></select></label>
      <label className="live-field"><span>زمان وقوع از</span><input type="datetime-local" step="1" dir="ltr" {...field('after')}/></label>
      <label className="live-field"><span>زمان وقوع تا</span><input type="datetime-local" step="1" dir="ltr" {...field('before')}/></label>
      <label><input type="checkbox" checked={draft.archivedDevices} onChange={event=>setDraft(value=>({...value,archivedDevices:event.target.checked}))}/> شامل دستگاه‌های بایگانی‌شده</label>
      <label><input type="checkbox" checked={draft.archivedCustomers} onChange={event=>setDraft(value=>({...value,archivedCustomers:event.target.checked}))}/> شامل سازمان‌های بایگانی‌شده</label>
      <div className="live-event-filter-actions"><button className="live-primary" type="submit">اعمال فیلترها</button><button className="live-secondary" type="button" onClick={reset}>پاک کردن فیلترها</button></div>
    </form>
    <p className="live-hint">بازه بر اساس زمان وقوع است؛ زمان‌ها با منطقهٔ زمانی مرورگر ({Intl.DateTimeFormat().resolvedOptions().timeZone}) وارد می‌شوند.</p>
    {validation&&<p className="live-error" role="alert">{validation}</p>}
    {error&&<p className="live-error" role="alert">{error}<button type="button" onClick={()=>setRevision(value=>value+1)}>تلاش دوباره</button></p>}
    <div aria-busy={busy}>
      {busy?<p role="status">در حال دریافت رویدادها…</p>:!error&&result&&<>
        <EventTable events={result.results}/>
        <nav className="live-pagination" aria-label="صفحه‌بندی رویدادها">
          <button className="live-secondary" disabled={!result.previous} onClick={()=>setPage(value=>value-1)}>صفحه قبل</button>
          <span role="status">صفحه {page.toLocaleString('fa-IR')} · {result.count.toLocaleString('fa-IR')} رویداد</span>
          <button className="live-secondary" disabled={!result.next} onClick={()=>setPage(value=>value+1)}>صفحه بعد</button>
          <button className="live-secondary" onClick={()=>setRevision(value=>value+1)}>بازخوانی</button>
        </nav>
      </>}
    </div>
  </section>;
}
