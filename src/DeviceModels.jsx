import RowAction from './RowAction.jsx';
import RecordHistory, { RecordHistoryHeaders, RecordHistoryCells } from './RecordHistory.jsx';
import React, { useState } from 'react';
import { Box, Cpu, FlaskConical, Layers, Monitor, Plus } from 'lucide-react';
import Dialog from './Dialog.jsx';
import { api } from './api.js';
import ListStatusFilter from './ListStatusFilter.jsx';

const kinds = [['unit', 'یونیت', Cpu], ['cr', 'کامان‌ریل', Layers], ['combo', 'ترکیبی یونیت و کامان‌ریل', Layers], ['pump', 'تست پمپ', FlaskConical], ['pro', 'تست کامل', Cpu]];
const editions = [['b', 'باکس کنار دستگاه', Box], ['pc', 'کامپیوتری', Monitor], ['e', 'اقتصادی', Cpu]];

export function DeviceModelSelect({ models, editing }) {
  return <label className="live-field"><span>مدل دستگاه</span><select name="device_model" required={!editing || Boolean(editing.device_model)} defaultValue={editing?.device_model || ''}>
    <option value="">{editing && !editing.device_model ? `مدل قدیمی: ${editing.model_name} · بدون تغییر` : 'انتخاب مدل دستگاه'}</option>
    {models.filter(model => model.is_active || model.id === editing?.device_model).map(model => <option key={model.id} value={model.id}>{model.display_name} · {model.code}{!model.is_active ? ' · غیرفعال' : ''}</option>)}
  </select>{editing && !editing.device_model && <small>مدل قدیمی حفظ می‌شود؛ فقط با انتخاب مدل جدید تغییر می‌کند.</small>}</label>;
}

export default function DeviceModels({ models, canEdit, onSaved, onSessionExpired, status, onStatus, loading, loadError }) {
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState('unit');
  const [edition, setEdition] = useState('b');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  function edit(model = null) {
    setEditing(model); setKind(model?.kind || 'unit'); setEdition(model?.edition || 'b'); setError(''); setOpen(true);
  }
  async function save(event) {
    event.preventDefault(); setBusy(true); setError('');
    const form = new FormData(event.currentTarget);
    const data = { display_name: form.get('display_name'), is_active: form.get('is_active') === 'on' };
    try {
      if (editing) await api.updateDeviceModel(editing.id, data);
      else await api.createDeviceModel({ ...data, kind, edition, code: form.get('code').trim().toUpperCase() });
      setOpen(false); await onSaved();
    } catch (cause) {
      if ([401, 403].includes(cause.status)) onSessionExpired();
      else setError(cause.message);
    } finally { setBusy(false); }
  }
  return <section className="live-card"><div className="live-section-heading"><div><h2>کاتالوگ مدل‌های دستگاه</h2><p>نوع، نسخه و کد ثابت هر مدل؛ هر مشتری می‌تواند چند دستگاه داشته باشد.</p></div>{canEdit && <button className="live-primary" onClick={() => edit()}><Plus size={16}/>تعریف مدل</button>}</div>
    <ListStatusFilter kind="account" label="وضعیت مدل" value={status} onChange={onStatus}/>
    {loading ? <p role="status">در حال دریافت مدل‌ها…</p> : !loadError && (!models.length ? <p className="live-empty">مدلی با این وضعیت برای نمایش وجود ندارد.</p> : <div className="live-table-wrap"><table className="live-table"><thead><tr><th>کد مدل</th><th>نام نمایشی</th><th>نوع دستگاه</th><th>نسخه</th><th>وضعیت</th><RecordHistoryHeaders/>{canEdit && <th>عملیات</th>}</tr></thead><tbody>{models.map(model => <tr key={model.id}><td dir="ltr">{model.code}</td><td>{model.display_name}</td><td>{model.kind_label}</td><td>{model.edition_label}</td><td>{model.is_active ? 'فعال' : 'غیرفعال'}</td><RecordHistoryCells record={model}/>{canEdit && <td className="live-row-actions"><RowAction action="edit" label={`ویرایش مدل ${model.code}`} onClick={() => edit(model)}/></td>}</tr>)}</tbody></table></div>)}
    {open && <Dialog title={editing ? 'ویرایش مدل دستگاه' : 'تعریف مدل دستگاه'} onClose={() => setOpen(false)}><form onSubmit={save}>{editing&&<RecordHistory record={editing}/>}
      <fieldset className="model-choices" disabled={Boolean(editing)}><legend>نوع دستگاه</legend>{kinds.map(([value, title, Icon]) => <label key={value}><input type="radio" name="kind" value={value} checked={kind === value} onChange={() => setKind(value)}/><Icon/><span>{title}</span></label>)}</fieldset>
      <fieldset className="model-choices model-editions" disabled={Boolean(editing)}><legend>نسخه دستگاه</legend>{editions.map(([value, title, Icon]) => <label key={value}><input type="radio" name="edition" value={value} checked={edition === value} onChange={() => setEdition(value)}/><Icon/><span>{title}</span></label>)}</fieldset>
      <label className="live-field"><span>کد مدل</span><input name="code" dir="ltr" required={!editing} maxLength={120} pattern="[A-Za-z][A-Za-z0-9]*(-[A-Za-z0-9]+)*" defaultValue={editing?.code || ''} disabled={Boolean(editing)} placeholder="AD-UNIT-PC"/></label>
      <label className="live-field"><span>نام نمایشی</span><input name="display_name" required maxLength={200} defaultValue={editing?.display_name || ''}/></label>
      <label><input type="checkbox" name="is_active" defaultChecked={editing?.is_active ?? true}/> قابل انتخاب برای دستگاه جدید</label>
      <p className="live-hint">کد، نوع و نسخه پس از ثبت ثابت می‌مانند تا سازگاری بسته‌های نرم‌افزار تغییر نکند. غیرفعال‌کردن مدل، دستگاه‌های قبلی را حذف نمی‌کند.</p>
      {error && <p className="live-error" role="alert">{error}</p>}<footer><button className="live-secondary" type="button" onClick={() => setOpen(false)}>انصراف</button><button className="live-primary" disabled={busy}>{busy ? 'در حال ذخیره…' : 'ذخیره مدل'}</button></footer>
    </form></Dialog>}
  </section>;
}
