import React, { useCallback, useEffect, useState } from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import { api } from './api.js';
import Dialog from './Dialog.jsx';
import { formatDate } from './EventTable.jsx';

const text = {
  title: 'کاربران سامانه',
  description: 'حساب کارکنان توسط مدیر کل ایجاد می‌شود؛ ثبت‌نام عمومی وجود ندارد.',
  add: 'افزودن کاربر',
  email: 'ایمیل',
  firstName: 'نام',
  lastName: 'نام خانوادگی',
  password: 'گذرواژهٔ اولیه',
  role: 'نقش',
  support: 'پشتیبان',
  superAdmin: 'مدیر کل',
  status: 'وضعیت',
  active: 'فعال',
  inactive: 'غیرفعال',
  created: 'تاریخ ایجاد',
  cancel: 'انصراف',
  close: 'بستن',
  refresh: 'بازخوانی',
  loading: 'در حال دریافت کاربران…',
  saving: 'در حال ایجاد حساب…',
  success: 'حساب کاربر ایجاد شد و آمادهٔ ورود است.',
  empty: 'کاربری برای نمایش وجود ندارد.',
  passwordHint: 'حداقل ۸ نویسه؛ از گذرواژهٔ رایج یا مشابه نام و ایمیل استفاده نکنید. گذرواژه را از مسیر امن به کاربر تحویل دهید.',
  adminHint: 'مدیر کل می‌تواند کاربران، مشتریان، دستگاه‌ها و انتشار نسخه‌ها را مدیریت کند.',
  loadError: 'دریافت کاربران انجام نشد. دوباره تلاش کنید.',
  saveError: 'حساب ایجاد نشد. اطلاعات را بررسی کنید.',
};

function message(error, fallback) {
  if (!error.data || !Object.keys(error.data).length) return fallback;
  const fields = { first_name: text.firstName, last_name: text.lastName, detail: 'خطا', non_field_errors: 'اطلاعات' };
  const errors = { 'A user with this email already exists.': 'حسابی با این ایمیل از قبل وجود دارد.' };
  return Object.entries(error.data).map(([key, value]) =>
    `${fields[key] || text[key] || key}: ${(Array.isArray(value) ? value : [value]).map((item) => errors[item] || item).join(' ')}`,
  ).join(' · ');
}

export default function StaffUsers({ onSessionExpired, refreshKey }) {
  const [payload, setPayload] = useState(null);
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    api.staffUsers({ page }, { signal: controller.signal }).then(setPayload).catch((cause) => {
      if (controller.signal.aborted) return;
      if (cause.status === 401 || cause.status === 403) onSessionExpired();
      else setError(text.loadError);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [page, refresh, refreshKey, onSessionExpired]);

  const close = useCallback(() => { if (!saving) { setOpen(false); setFormError(''); } }, [saving]);

  async function create(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    setSaving(true);
    setFormError('');
    try {
      await api.createStaffUser(data);
      form.reset();
      setOpen(false);
      setNotice(text.success);
      setPage(1);
      setRefresh((value) => value + 1);
    } catch (cause) {
      if (cause.status === 401 || cause.status === 403) onSessionExpired();
      else setFormError(message(cause, text.saveError));
    } finally { setSaving(false); }
  }

  return <section className="live-card" aria-labelledby="staff-users-title">
    <div className="live-section-heading"><div><h2 id="staff-users-title">{text.title}</h2><p>{text.description}</p></div><div className="live-actions">
      <button className="live-icon" onClick={() => setRefresh((value) => value + 1)} aria-label={text.refresh} disabled={loading}><RefreshCw size={17}/></button>
      <button className="live-primary" onClick={() => { setNotice(''); setOpen(true); }}><Plus size={16}/>{text.add}</button>
    </div></div>
    {notice && <p role="status">{notice}</p>}
    {error && <p className="live-error" role="alert">{error}</p>}
    {loading && <p role="status">{text.loading}</p>}
    {!loading && !error && <>
      {payload?.results?.length ? <div className="live-table-wrap"><table className="live-table"><thead><tr><th>{text.firstName}</th><th>{text.email}</th><th>{text.role}</th><th>{text.status}</th><th>{text.created}</th></tr></thead><tbody>
        {payload.results.map((user) => <tr key={user.id}><td>{[user.first_name, user.last_name].filter(Boolean).join(' ') || '—'}</td><td dir="ltr">{user.email}</td><td>{user.role === 'super_admin' ? text.superAdmin : text.support}</td><td>{user.is_active ? text.active : text.inactive}</td><td>{formatDate(user.date_joined)}</td></tr>)}
      </tbody></table></div> : <p>{text.empty}</p>}
      <div className="live-staff-pagination"><button className="live-secondary" disabled={!payload?.previous} onClick={() => setPage((value) => value - 1)}>قبلی</button><span>صفحهٔ {page.toLocaleString('fa-IR')} · {Number(payload?.count || 0).toLocaleString('fa-IR')} کاربر</span><button className="live-secondary" disabled={!payload?.next} onClick={() => setPage((value) => value + 1)}>بعدی</button></div>
    </>}
    {open && <Dialog title={text.add} onClose={close} dismissible={!saving}>
      <form onSubmit={create}>
        <label className="live-field"><span>{text.firstName}</span><input name="first_name" maxLength={150} autoComplete="given-name" disabled={saving}/></label>
        <label className="live-field"><span>{text.lastName}</span><input name="last_name" maxLength={150} autoComplete="family-name" disabled={saving}/></label>
        <label className="live-field"><span>{text.email}</span><input name="email" type="email" dir="ltr" maxLength={254} autoComplete="off" required disabled={saving}/></label>
        <label className="live-field"><span>{text.password}</span><input name="password" type="password" dir="ltr" autoComplete="new-password" minLength={8} maxLength={128} required aria-describedby="staff-password-hint" disabled={saving}/></label>
        <p id="staff-password-hint" className="live-hint">{text.passwordHint}</p>
        <label className="live-field"><span>{text.role}</span><select name="role" defaultValue="support" aria-describedby="staff-role-hint" disabled={saving}><option value="support">{text.support}</option><option value="super_admin">{text.superAdmin}</option></select></label>
        <p id="staff-role-hint" className="live-hint">{text.adminHint}</p>
        {formError && <p className="live-error" role="alert">{formError}</p>}
        <footer><button type="button" className="live-secondary" disabled={saving} onClick={close}>{text.cancel}</button><button className="live-primary" disabled={saving}>{saving ? text.saving : text.add}</button></footer>
      </form>
    </Dialog>}
  </section>;
}
