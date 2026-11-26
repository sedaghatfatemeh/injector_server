import RowAction from './RowAction.jsx';
import { RecordHistoryHeaders, RecordHistoryCells } from './RecordHistory.jsx';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import { api } from './api.js';
import Dialog from './Dialog.jsx';
import { customerAccountText as t } from './locale.js';
import ListStatusFilter from './ListStatusFilter.jsx';

export default function CustomerUsers({ onSessionExpired }) {
  const [payload, setPayload] = useState(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [query, setQuery] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [notice, setNotice] = useState('');
  const [organizations, setOrganizations] = useState(null);
  const [orgSearch, setOrgSearch] = useState('');
  const [orgPage, setOrgPage] = useState(1);
  const [organization, setOrganization] = useState('');
  const [orgLoading, setOrgLoading] = useState(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setPayload(null);
    api.customerUsers({ page, search: query, ...(status ? { is_active: status } : {}) }, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setPayload(value);
    }).catch(cause => {
      if (controller.signal.aborted) return;
      if (cause.status === 401 || cause.status === 403) onSessionExpired();
      else setError(t.error);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [page, query, status, refresh, onSessionExpired]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setOrgLoading(true); setOrganizations(null);
    api.customers({ search: orgSearch, page: orgPage, is_archived: 'false' }, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setOrganizations(value);
    }).catch(cause => {
      if (controller.signal.aborted) return;
      if (cause.status === 401 || cause.status === 403) onSessionExpired();
      else setFormError(t.error);
    }).finally(() => { if (!controller.signal.aborted) setOrgLoading(false); });
    return () => controller.abort();
  }, [open, orgSearch, orgPage, onSessionExpired]);

  const close = useCallback(() => { if (!saving) { setOpen(false); setFormError(''); } }, [saving]);
  async function create(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    data.customer = Number(organization);
    setSaving(true); setFormError('');
    try {
      await api.createCustomerUser(data);
      if (!alive.current) return;
      form.reset(); setOpen(false); setNotice(t.created); setPage(1); setRefresh(value => value + 1);
    } catch (cause) {
      if (!alive.current) return;
      if (cause.status === 401 || cause.status === 403) onSessionExpired();
      else if (cause.data?.email) setFormError('این ایمیل معتبر نیست یا حسابی با آن وجود دارد.');
      else if (cause.data?.password) setFormError('گذرواژه شرایط امنیتی را ندارد؛ گذرواژهٔ قوی‌تری انتخاب کنید.');
      else setFormError(t.error);
    } finally { if (alive.current) setSaving(false); }
  }

  async function toggle(user) {
    setSaving(true); setError(''); setNotice('');
    try {
      await api.setCustomerUserActive(user.id, !user.is_active);
      if (alive.current) { setNotice(t.changed); setPage(1); setRefresh(value => value + 1); }
    } catch (cause) {
      if (!alive.current) return;
      if (cause.status === 401 || cause.status === 403) onSessionExpired();
      else setError(t.error);
    } finally { if (alive.current) setSaving(false); }
  }

  return <section className="live-card" aria-labelledby="customer-users-title">
    <ListStatusFilter kind="account" value={status} onChange={value => { setStatus(value); setPage(1); }}/>
    <div className="live-section-heading"><div><h2 id="customer-users-title">{t.title}</h2><p>{t.description}</p></div><div className="live-actions">
      <button className="live-icon" onClick={() => setRefresh(v => v + 1)} aria-label={t.refresh} disabled={loading}><RefreshCw size={17}/></button>
      <button className="live-primary" onClick={() => { setOrganization(''); setOrgSearch(''); setOrgPage(1); setNotice(''); setOpen(true); }}><Plus size={16}/>{t.add}</button>
    </div></div>
    <label className="live-field"><span>{t.accountSearch}</span><input value={query} onChange={e => { setQuery(e.target.value); setPage(1); }}/></label>
    {notice && <p role="status">{notice}</p>}{error && <p className="live-error" role="alert">{error}</p>}
    {loading && <p role="status">{t.loading}</p>}
    {!loading && !error && <>{payload?.results?.length ? <div className="live-table-wrap"><table className="live-table"><thead><tr><th>{t.email}</th><th>{t.customer}</th><th>{t.status}</th><RecordHistoryHeaders/><th>عملیات</th></tr></thead><tbody>
      {payload.results.map(user => <tr key={user.id}><td dir="ltr">{user.email}</td><td>{user.organization.name}</td><td>{user.is_active ? t.active : t.inactive}{user.organization.is_archived && <small>{t.archived}</small>}</td><RecordHistoryCells record={user}/><td className="live-row-actions"><RowAction action="toggle" danger={user.is_active} disabled={saving || (!user.is_active && user.organization.is_archived)} onClick={() => toggle(user)} label={`${user.is_active ? t.deactivate : t.activate} ${user.email}`}/></td></tr>)}
    </tbody></table></div> : <p>{t.empty}</p>}
      <div className="live-staff-pagination"><button className="live-secondary" disabled={!payload?.previous} onClick={() => setPage(v => v - 1)}>{t.previous}</button><span>{Number(payload?.count || 0).toLocaleString('fa-IR')}</span><button className="live-secondary" disabled={!payload?.next} onClick={() => setPage(v => v + 1)}>{t.next}</button></div></>}
    {open && <Dialog title={t.add} onClose={close} dismissible={!saving}><form onSubmit={create}>
      {['first_name', 'last_name', 'email', 'password'].map(name => <label className="live-field" key={name}><span>{t[name]}</span><input name={name} type={name === 'email' ? 'email' : name === 'password' ? 'password' : 'text'} dir={['email', 'password'].includes(name) ? 'ltr' : 'rtl'} maxLength={name === 'password' ? 128 : name === 'email' ? 254 : 150} minLength={name === 'password' ? 8 : undefined} required={['email', 'password'].includes(name)} autoComplete={name === 'password' ? 'new-password' : 'off'} disabled={saving}/></label>)}
      <p className="live-hint">{t.passwordHint}</p>
      <label className="live-field"><span>{t.organizationSearch}</span><input value={orgSearch} disabled={saving} onChange={e => { setOrgSearch(e.target.value); setOrgPage(1); setOrganization(''); }}/></label>
      <label className="live-field"><span>{t.customer}</span><select aria-label={t.customer} required value={organization} disabled={saving || orgLoading} onChange={e => setOrganization(e.target.value)}><option value="">{t.choose}</option>{organizations?.results?.map(org => <option key={org.id} value={org.id}>{org.organization_name}</option>)}</select></label>
      {orgLoading && <p role="status">{t.loading}</p>}{!orgLoading && !organizations?.results?.length && <p>{t.noOrganizations}</p>}
      <div className="live-staff-pagination"><button type="button" className="live-secondary" disabled={!organizations?.previous || saving || orgLoading} onClick={() => { setOrgPage(v => v - 1); setOrganization(''); }}>{t.previous}</button><button type="button" className="live-secondary" disabled={!organizations?.next || saving || orgLoading} onClick={() => { setOrgPage(v => v + 1); setOrganization(''); }}>{t.next}</button></div>
      {formError && <p className="live-error" role="alert">{formError}</p>}
      <footer><button type="button" className="live-secondary" disabled={saving} onClick={close}>{t.cancel}</button><button className="live-primary" disabled={saving || orgLoading || !organization}>{saving ? t.saving : t.add}</button></footer>
    </form></Dialog>}
  </section>;
}
