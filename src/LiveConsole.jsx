import RowAction from './RowAction.jsx';
import RecordHistory, { RecordHistoryHeaders, RecordHistoryCells } from './RecordHistory.jsx';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, Check, Cpu, Download, FileClock, LogOut, Menu, Moon, Plus, RefreshCw, Search, ShieldCheck, Sun, X } from 'lucide-react';
import { api } from './api.js';
import './live.css';
import EventHistory from './EventHistory.jsx';
import EventTable, { labels, formatDate, Status, Empty } from './EventTable.jsx';
import StaffUsers from './StaffUsers.jsx';
import CustomerUsers from './CustomerUsers.jsx';
import CustomerPanel from './CustomerPanel.jsx';
import Dialog from './Dialog.jsx';
import { readTheme, rememberTheme, shellText } from './locale.js';
import DashboardOverview, { BrandMark, StaffMasthead } from './DashboardOverview.jsx';
import './dashboard.css';
import DeviceModels, { DeviceModelSelect } from './DeviceModels.jsx';
import './device-models.css';
import ListStatusFilter, { ListPagination } from './ListStatusFilter.jsx';

function rows(payload) {
  return Array.isArray(payload) ? payload : payload?.results || [];
}

function Field({ label, children, dir }) {
  return <label className="live-field"><span>{label}</span>{React.cloneElement(children, { dir: dir || children.props.dir })}</label>;
}

function ArchiveBadge() { return <span className="live-status">بایگانی‌شده</span>; }
function ArchivedNotice() { return <p className="live-hint">این دستگاه بایگانی شده است؛ جزئیات و تاریخچه فقط برای مشاهده نمایش داده می‌شوند.</p>; }

export default function LiveConsole() {
  const [authenticated, setAuthenticated] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('support');
  const [organization, setOrganization] = useState(null);
  const [showPassword, setShowPassword] = useState(false);
  const [theme, setTheme] = useState(readTheme);
  const [page, setPage] = useState('overview');
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [summary, setSummary] = useState(null);
  const [devices, setDevices] = useState([]);
  const [deviceModels, setDeviceModels] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [eventRefresh, setEventRefresh] = useState(0);
  const [releases, setReleases] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [query, setQuery] = useState('');
  const [onlineFilter, setOnlineFilter] = useState('');
  const [archiveStatus, setArchiveStatus] = useState('active');
  const [inventoryPage, setInventoryPage] = useState(1);
  const [inventoryMeta, setInventoryMeta] = useState(null);
  const [modelStatus, setModelStatus] = useState('');
  const [releaseStatus, setReleaseStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [modal, setModal] = useState('');
  const [editing, setEditing] = useState(null);
  const [selected, setSelected] = useState(null);
  const [selectedEvents, setSelectedEvents] = useState([]);
  const [selectedUpdates, setSelectedUpdates] = useState([]);
  const [oneTimeCredential, setOneTimeCredential] = useState('');

  const isAdmin = role === 'super_admin';
  const dataRevision = useRef(0);
  const resetSession = useCallback((message = '') => {
    dataRevision.current += 1;
    setAuthenticated(false);
    setBusy(false);
    setNavigationOpen(false);
    setRole('support');
    setOrganization(null);
    setShowPassword(false);
    setPage('overview');
    setArchiveStatus('active'); setInventoryPage(1); setInventoryMeta(null);
    setModelStatus(''); setReleaseStatus('');
    setModal('');
    setEditing(null);
    setSelected(null);
    setSelectedEvents([]);
    setSelectedUpdates([]);
    setOneTimeCredential('');
    setSummary(null);
    setDevices([]);
    setDeviceModels([]);
    setCustomers([]);
    setReleases([]);
    setAssignments([]);
    setPassword('');
    setNotice('');
    setError(message);
  }, []);
  const sessionExpired = useCallback(() => resetSession('نشست شما پایان یافته یا دسترسی شما تغییر کرده است. دوباره وارد شوید.'), [resetSession]);
  const loadData = useCallback(async () => {
    if (!authenticated || ['users', 'customer-users'].includes(page) || role === 'customer') return;
    const revision = ++dataRevision.current;
    setBusy(true);
    setError('');
    try {
      if (['devices', 'customers', 'releases'].includes(page)) setInventoryMeta(null);
      const deviceParams = {};
      if (page === 'devices') Object.assign(deviceParams, { archive_status: archiveStatus, page: inventoryPage });
      if (query.trim() && ['devices', 'customers'].includes(page)) {
        if (page === 'devices') deviceParams.search = query.trim();
      }
      if (page === 'devices' && onlineFilter) deviceParams.online = onlineFilter;
      if (page === 'overview') deviceParams.ordering = '-created_at';
      const customerParams = {};
      if (page === 'customers') customerParams.search = query.trim();
      if (page === 'customers') Object.assign(customerParams, { archive_status: archiveStatus, page: inventoryPage });
      const [nextSummary, nextDevices, nextCustomers, nextReleases, nextAssignments, nextModels] = await Promise.all([
        api.summary(), api.devices(deviceParams), api.customers(customerParams),
        api.releases(page === 'releases' ? { page: inventoryPage, ...(releaseStatus ? { status: releaseStatus } : {}) } : {}), api.assignments(),
        api.deviceModels(page === 'models' && modelStatus ? { is_active: modelStatus } : {}),
      ]);
      if (revision !== dataRevision.current) return;
      setSummary(nextSummary);
      setDevices(rows(nextDevices));
      if (['devices', 'customers', 'releases'].includes(page)) setInventoryMeta(page === 'devices' ? nextDevices : page === 'customers' ? nextCustomers : nextReleases);
      setDeviceModels(nextModels);
      setCustomers(rows(nextCustomers));
      setReleases(rows(nextReleases));
      setAssignments(rows(nextAssignments));
    } catch (cause) {
      if (revision !== dataRevision.current) return;
      setError(cause.status === 403 ? 'نشست شما پایان یافته است. دوباره وارد شوید.' : cause.message || 'دریافت اطلاعات انجام نشد.');
      if (cause.status === 401 || cause.status === 403) sessionExpired();
    } finally {
      if (revision === dataRevision.current) setBusy(false);
    }
  }, [authenticated, page, role, query, onlineFilter, archiveStatus, inventoryPage, modelStatus, releaseStatus, sessionExpired]);

  useEffect(() => {
    rememberTheme(theme);
  }, [theme]);

  useEffect(() => {
    let current = true;
    api.csrf().then(() => api.session()).then((session) => {
      if (current) { setRole(session.role); setOrganization(session.organization || null); setEmail(session.email); setAuthenticated(true); }
    }).catch((cause) => {
      if (current) {
        setAuthenticated(false);
        if (cause.status !== 401 && cause.status !== 403) setError(shellText.connectionError);
      }
    }).finally(() => {
      if (current) setInitializing(false);
    });
    return () => { current = false; };
  }, []);

  useEffect(() => {
    loadData();
    return () => { dataRevision.current += 1; };
  }, [loadData]);

  async function signIn(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.csrf();
      const result = await api.login(email.trim(), password);
      setRole(result.role);
      setOrganization(result.organization || null);
      if (result.role !== 'customer' && window.location.pathname.startsWith('/customer/')) window.history.replaceState(null, '', '/');
      setAuthenticated(true);
      setPassword('');
    } catch (cause) {
      setError(cause.message || 'ورود انجام نشد. ایمیل و گذرواژه را بررسی کنید.');
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    try { await api.logout(); resetSession(); } catch (cause) { setError(cause.message); }
  }

  async function submitForm(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const value = Object.fromEntries(form.entries());
    setBusy(true);
    setError('');
    try {
      if (modal === 'customer') {
        const data = { ...value, contact_email: value.contact_email.trim().toLowerCase() };
        if (editing) await api.updateCustomer(editing.id, data); else await api.createCustomer(data);
        setNotice(editing ? 'اطلاعات مشتری ذخیره شد.' : 'مشتری ثبت شد.');
      } else if (modal === 'device') {
        const data = { ...value, customer: Number(value.customer) };
        if (value.device_model) data.device_model = Number(value.device_model); else delete data.device_model;
        if (editing) await api.updateDevice(editing.id, data); else await api.createDevice(data);
        setNotice(editing ? 'اطلاعات دستگاه ذخیره شد.' : 'دستگاه ثبت شد.');
      } else if (modal === 'release') {
        const targets = form.getAll('target_devices').map(Number);
        const data = {
          version: value.version,
          package_url: value.package_url,
          sha256: value.sha256,
          compatible_models: value.compatible_models.split(',').map((item) => item.trim()).filter(Boolean),
          minimum_version: value.minimum_version,
          release_notes: value.release_notes,
          target_all_devices: value.target_mode === 'all',
          target_devices: value.target_mode === 'selected' ? targets : [],
        };
        await api.createRelease(data);
        setNotice('نسخه ثبت و برای دستگاه‌های سازگار منتشر شد.');
      }
      setModal('');
      setEditing(null);
      await loadData();
    } catch (cause) {
      const messages = cause.data ? Object.entries(cause.data).map(([key, val]) => `${key}: ${Array.isArray(val) ? val.join(' ') : val}`).join(' · ') : cause.message;
      setError(messages || 'ذخیره‌سازی انجام نشد.');
    } finally {
      setBusy(false);
    }
  }

  async function archiveRecord(kind, record) {
    if (!window.confirm(`«${kind === 'device' ? record.serial_number : record.organization_name}» بایگانی شود؟`)) return;
    try {
      if (kind === 'device') await api.archiveDevice(record.id); else await api.archiveCustomer(record.id);
      setNotice('رکورد بایگانی شد.');
      setInventoryPage(1);
      await loadData();
    } catch (cause) { setError(cause.message); }
  }

  async function provision(device) {
    try {
      const result = await api.provisionDevice(device.id);
      setOneTimeCredential(result.credential);
    } catch (cause) { setError(cause.message); }
  }

  async function withdraw(release) {
    if (!window.confirm(`نسخهٔ ${release.version} پس‌گرفته شود؟`)) return;
    try { await api.withdrawRelease(release.id); setNotice('نسخه پس گرفته شد.'); setInventoryPage(1); await loadData(); }
    catch (cause) { setError(cause.message); }
  }

  async function assignRollback(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const deviceIds = form.getAll('rollback_devices').map(Number);
    const reason = String(form.get('reason') || '').trim();
    try {
      await api.rollbackRelease(editing.id, { device_ids: deviceIds, reason });
      setModal(''); setEditing(null); setNotice('نسخهٔ قبلی برای دستگاه‌های انتخاب‌شده تخصیص یافت.'); await loadData();
    } catch (cause) { setError(cause.message); }
  }

  async function openDevice(device) {
    setSelected(device);
    setSelectedEvents([]);
    setSelectedUpdates([]);
    try {
      const historyParams = new URLSearchParams();
      if (device.is_archived) historyParams.set('is_archived', 'true');
      if (device.customer_is_archived) historyParams.set('device__customer__is_archived', 'true');
      const [history, updateHistory] = await Promise.all([
        api.request(`/api/v1/devices/${device.id}/events/?${historyParams}`),
        api.request(`/api/v1/devices/${device.id}/updates/?${historyParams}`),
      ]);
      setSelectedEvents(rows(history));
      setSelectedUpdates(rows(updateHistory));
    } catch (cause) { setError(cause.message); }
  }

  const menu = [
    ['overview', shellText.overview, Activity], ['devices', shellText.devices, Cpu], ['customers', shellText.customers, ShieldCheck],
    ['models', 'مدل‌های دستگاه', Cpu], ['events', shellText.events, FileClock], ['releases', shellText.releases, Download],
    ...(isAdmin ? [['users', shellText.users, ShieldCheck], ['customer-users', shellText.customerUsers, ShieldCheck]] : []),
  ];

  function navigate(next) {
    setPage(next); setQuery(''); setArchiveStatus('active'); setOnlineFilter('');
    setInventoryPage(1); setInventoryMeta(null); setNavigationOpen(false); setSelected(null);
  }
  function changeArchive(value) { setArchiveStatus(value); setInventoryPage(1); setInventoryMeta(null); }
  function changeQuery(value) { setQuery(value); setInventoryPage(1); setInventoryMeta(null); }

  const navigation = <nav aria-label={shellText.navigation}>{menu.map(([key, title, Icon]) =>
    <button key={key} aria-current={page === key ? 'page' : undefined} className={page === key ? 'selected' : ''}
      onClick={() => navigate(key)}><Icon size={18}/>{title}</button>,
  )}</nav>;

  if (initializing) return <main className="live-app" dir="rtl"><section className="live-login"><p role="status">{shellText.restoringSession}</p></section></main>;

  if (!authenticated) {
    return <main className="live-app" dir="rtl"><section className="live-login"><div className="live-brand"><Cpu/><div><b>پیشگامان شرق</b><span>سامانه مدیریت دستگاه‌ها</span></div></div><h1>ورود به سامانه</h1><p>با حساب ایجادشده توسط مدیر کل وارد شوید.</p>
      {initializing && <p role="status">در حال اتصال به سامانه…</p>}
      <form onSubmit={signIn}><Field label="ایمیل"><input name="email" type="email" dir="ltr" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)}/></Field><Field label="گذرواژه"><input name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)}/></Field><button type="button" className="live-secondary" aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? 'پنهان‌کردن گذرواژه' : 'نمایش گذرواژه'}</button>{error&&<p className="live-error" role="alert">{error}</p>}<button className="live-primary" disabled={busy}>{busy?'در حال ورود…':'ورود'}</button></form>
      <button className="live-theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun/> : <Moon/>} تغییر پوسته</button></section></main>;
  }

  if (role === 'customer') return <CustomerPanel organization={organization} email={email} theme={theme}
    onTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')} onLogout={signOut} onSessionExpired={sessionExpired} parentError={error}/>;

  return <main className="live-app staff-dashboard" dir="rtl"><a className="live-skip" href="#live-content">{shellText.skipNavigation}</a><aside className="live-sidebar"><div className="live-brand"><BrandMark/><div><b>پیشگامان شرق</b><span>مدیریت ناوگان</span></div></div>{navigation}<div className="live-sidebar-foot"><span>{isAdmin?'مدیر کل':'پشتیبان'}</span><button onClick={signOut}><LogOut size={16}/> خروج</button></div></aside>
    <section className="live-main" id="live-content" tabIndex={-1}><StaffMasthead isAdmin={isAdmin}/><header className="live-top"><div><h1>{menu.find(([key])=>key===page)?.[1]}</h1><p>{busy?'در حال دریافت اطلاعات…':`آخرین به‌روزرسانی: ${formatDate(summary?.generated_at)}`}</p></div><div className="live-actions"><button className="live-icon live-menu-toggle" aria-label={shellText.openNavigation} aria-haspopup="dialog" aria-expanded={navigationOpen} onClick={() => setNavigationOpen(true)}><Menu size={18}/></button><button className="live-icon" onClick={() => { loadData(); setEventRefresh(value => value + 1); }} aria-label="بازخوانی"><RefreshCw size={17}/></button><button className="live-icon" onClick={() => setTheme(theme === 'dark'?'light':'dark')} aria-label="تغییر پوسته">{theme==='dark'?<Sun size={17}/>:<Moon size={17}/>}</button><button className="live-icon" onClick={signOut} aria-label="خروج"><LogOut size={17}/></button></div></header>
      {error&&<div className="live-error" role="alert">{error}<button onClick={() => setError('')} aria-label="بستن"><X size={15}/></button></div>}
      {page==='overview'&&<DashboardOverview summary={summary} devices={devices} busy={busy} isAdmin={isAdmin} onDevice={openDevice} onNavigate={navigate}/>}
      {page==='devices'&&<section className="live-card"><ListStatusFilter value={archiveStatus} onChange={changeArchive}/><Toolbar query={query} setQuery={changeQuery} placeholder="جست‌وجوی سریال، مشتری یا مدل" action={isAdmin?()=>{setEditing(null);setModal('device');}:null} actionLabel="ثبت دستگاه"/><div className="live-filter"><label>وضعیت اتصال<select value={onlineFilter} onChange={event=>{setOnlineFilter(event.target.value);setInventoryPage(1);}}><option value="">همه</option><option value="true">متصل</option><option value="false">قطع ارتباط</option></select></label></div>{busy?<p role="status">{shellText.loading}</p>:!error&&<DeviceTable filtered={Boolean(query.trim() || onlineFilter || archiveStatus !== 'active')} devices={devices} canEdit={isAdmin} onSelect={openDevice} onEdit={(record)=>{setEditing(record);setModal('device');}} onArchive={(record)=>archiveRecord('device',record)} onProvision={provision}/>}<ListPagination payload={inventoryMeta} page={inventoryPage} onPage={setInventoryPage} loading={busy}/></section>}
      {page==='customers'&&<section className="live-card"><ListStatusFilter value={archiveStatus} onChange={changeArchive}/><Toolbar query={query} setQuery={changeQuery} placeholder="جست‌وجوی نام سازمان یا تماس" action={isAdmin?()=>{setEditing(null);setModal('customer');}:null} actionLabel="ثبت مشتری"/>{busy?<p role="status">{shellText.loading}</p>:!error&&<CustomerTable filtered={Boolean(query.trim() || archiveStatus !== 'active')} customers={customers} canEdit={isAdmin} onEdit={(record)=>{setEditing(record);setModal('customer');}} onArchive={(record)=>archiveRecord('customer',record)}/>}<ListPagination payload={inventoryMeta} page={inventoryPage} onPage={setInventoryPage} loading={busy}/></section>}
      {page==='models'&&<DeviceModels loading={busy} loadError={error} status={modelStatus} onStatus={setModelStatus} models={deviceModels} canEdit={isAdmin} onSaved={loadData} onSessionExpired={sessionExpired}/>}
      {page==='events'&&<EventHistory refreshKey={eventRefresh} onSessionExpired={sessionExpired}/>}
      {page==='users'&&isAdmin&&<StaffUsers onSessionExpired={sessionExpired} refreshKey={eventRefresh}/>}
      {page==='customer-users'&&isAdmin&&<CustomerUsers onSessionExpired={sessionExpired}/>}
      {page==='releases'&&<section className="live-card"><ListStatusFilter kind="release" value={releaseStatus} onChange={value=>{setReleaseStatus(value);setInventoryPage(1);}}/><div className="live-section-heading"><div><h2>نسخه‌های برنامه</h2><p>بسته‌ها از میزبان HTTPS خارجی دریافت می‌شوند.</p></div>{isAdmin&&<button className="live-primary" onClick={()=>setModal('release')}><Plus size={16}/> ثبت نسخه</button>}</div>{busy?<p role="status">{shellText.loading}</p>:!error&&<ReleaseTable releases={releases} assignments={assignments} isAdmin={isAdmin} onWithdraw={withdraw} onRollback={(release)=>{setEditing(release);setModal('rollback');}}/>}<ListPagination payload={inventoryMeta} page={inventoryPage} onPage={setInventoryPage} loading={busy}/></section>}
      <footer className="live-footer">وضعیت آنلاین بر اساس آخرین ارتباط موفق و آستانهٔ {summary?.online_window_minutes ?? 15} دقیقه محاسبه می‌شود؛ این وضعیت ایمنی اجرای آزمون را تأیید نمی‌کند.</footer>
    </section>
    {navigationOpen&&<Dialog title={shellText.navigation} className="live-drawer" onClose={()=>setNavigationOpen(false)}>{navigation}</Dialog>}
    {modal&&<Dialog title={modal==='customer'?(editing?'ویرایش مشتری':'ثبت مشتری'):modal==='device'?(editing?'ویرایش دستگاه':'ثبت دستگاه'):modal==='rollback'?`تخصیص بازگشت نسخهٔ ${editing?.version}`:'ثبت نسخهٔ جدید'} onClose={()=>{setModal('');setError('');}} dismissible={!busy}><form onSubmit={modal==='rollback'?assignRollback:submitForm}>
      {modal==='customer'&&<><Field label="نام سازمان"><input name="organization_name" required maxLength="200" defaultValue={editing?.organization_name||''}/></Field><Field label="نام مسئول"><input name="contact_name" required maxLength="160" defaultValue={editing?.contact_name||''}/></Field><Field label="ایمیل"><input name="contact_email" type="email" dir="ltr" defaultValue={editing?.contact_email||''}/></Field><Field label="تلفن"><input name="contact_phone" dir="ltr" defaultValue={editing?.contact_phone||''}/></Field><Field label="نشانی"><textarea name="address" defaultValue={editing?.address||''}/></Field><Field label="یادداشت"><textarea name="notes" defaultValue={editing?.notes||''}/></Field></>}
      {modal==='device'&&<><Field label="شماره سریال"><input name="serial_number" dir="ltr" required maxLength="80" defaultValue={editing?.serial_number||''}/></Field><DeviceModelSelect models={deviceModels} editing={editing}/><Field label="مشتری"><select name="customer" required defaultValue={editing?.customer||''}><option value="" disabled>انتخاب مشتری</option>{editing?.customer&&!customers.some(item=>!item.is_archived&&item.id===editing.customer)&&<option value={editing.customer}>{editing.customer_name}{editing.customer_is_archived?' · بایگانی‌شده':''}</option>}{customers.filter(item=>!item.is_archived).map(item=><option key={item.id} value={item.id}>{item.organization_name}</option>)}</select></Field><Field label="نسخه برنامه"><input name="software_version" dir="ltr" readOnly={Boolean(editing?.last_seen_at)} defaultValue={editing?.software_version||''}/></Field>{editing?.last_seen_at&&<p className="live-hint">نسخهٔ فعلی با گزارش دستگاه به‌روز می‌شود.</p>}<Field label="موقعیت"><input name="location" defaultValue={editing?.location||''}/></Field><Field label="نام مسئول محل"><input name="site_contact_name" defaultValue={editing?.site_contact_name||''}/></Field><Field label="تلفن مسئول محل"><input name="site_contact_phone" dir="ltr" defaultValue={editing?.site_contact_phone||''}/></Field></>}
      {modal==='release'&&<><Field label="نسخه"><input name="version" dir="ltr" required placeholder="2.5.0"/></Field><Field label="پیوند بسته HTTPS"><input name="package_url" type="url" dir="ltr" required placeholder="https://packages.example/app.whl"/></Field><Field label="SHA-256"><input name="sha256" dir="ltr" required minLength="64" maxLength="64"/></Field><Field label="مدل‌های سازگار (با کاما جدا شوند)"><input name="compatible_models" dir="ltr" placeholder="خالی یعنی همهٔ مدل‌ها"/></Field><Field label="حداقل نسخهٔ فعلی"><input name="minimum_version" dir="ltr"/></Field><Field label="یادداشت نسخه"><textarea name="release_notes"/></Field><Field label="مقصد انتشار"><select name="target_mode"><option value="all">همهٔ دستگاه‌های سازگار</option><option value="selected">انتخاب دستگاه‌ها</option></select></Field><Field label="دستگاه‌های انتخابی"><select name="target_devices" multiple size="4">{devices.filter(item=>!item.is_archived).map(item=><option key={item.id} value={item.id}>{item.serial_number} · {item.model_name}</option>)}</select></Field><p className="live-hint">انتشار خودکار انجام می‌شود. دستگاه فقط در وضعیت امن و بیکار نصب را اجرا می‌کند. SHA-256 به‌تنهایی هویت ناشر را تأیید نمی‌کند.</p></>}
      {modal==='rollback'&&<><p className="live-hint">نسخهٔ {editing?.version} در نقطهٔ امن توسط خود دستگاه اعمال می‌شود.</p><Field label="دستگاه‌های مقصد"><select name="rollback_devices" multiple required size="6">{devices.filter(item=>!item.is_archived&&(!editing?.compatible_models?.length||editing.compatible_models.includes(item.model_name))).map(item=><option key={item.id} value={item.id}>{item.serial_number} · {item.model_name} · {item.software_version||'—'}</option>)}</select></Field><Field label="دلیل تخصیص"><textarea name="reason" required minLength="3"/></Field></>}
      {error&&<p className="live-error" role="alert">{error}</p>}<footer><button type="button" className="live-secondary" onClick={()=>setModal('')}>انصراف</button><button className="live-primary" disabled={busy}>{busy?'در حال ذخیره…':modal==='rollback'?'تخصیص بازگشت':'ذخیره'}</button></footer></form></Dialog>}
    {selected&&<Dialog title={`جزئیات دستگاه ${selected.serial_number}`} onClose={()=>setSelected(null)}>{selected.is_archived&&<ArchivedNotice/>}<dl className="live-detail"><dt>مشتری</dt><dd>{selected.customer_name}</dd><dt>مدل</dt><dd>{selected.model_display_name || selected.model_name}{selected.model_display_name && <small dir="ltr"> ? {selected.model_name}</small>}</dd><dt>نسخه</dt><dd>{selected.software_version||'—'}</dd><dt>آخرین ارتباط</dt><dd>{formatDate(selected.last_seen_at)}</dd><dt>وضعیت</dt><dd>{selected.is_online?'متصل':'قطع ارتباط'}</dd><dt>خطاهای فعال</dt><dd>{selected.active_fault_count||0}</dd><dt>محل</dt><dd>{selected.location||'—'}</dd></dl><RecordHistory record={selected} archive/><h3>رویدادهای دستگاه</h3><EventTable events={selectedEvents}/><h3>وضعیت به‌روزرسانی</h3>{selectedUpdates.map(item=><p key={item.id}>{item.release_version}: {labels[item.state]||item.state} · {formatDate(item.reported_at||item.updated_at)}</p>)}{isAdmin&&!selected.is_archived&&<footer><button className="live-primary" onClick={()=>provision(selected)}>صدور/چرخش شناسهٔ دستگاه</button></footer>}</Dialog>}
    {oneTimeCredential&&<Dialog title="شناسهٔ دستگاه — فقط همین‌بار نمایش داده می‌شود" onClose={()=>setOneTimeCredential('')}><p>این مقدار را در محل امن دستگاه ذخیره کنید.</p><code className="live-secret" dir="ltr">{oneTimeCredential}</code><button className="live-primary" onClick={async()=>{try { await navigator.clipboard.writeText(oneTimeCredential); setNotice('شناسه کپی شد.'); } catch { setError('کپی انجام نشد؛ شناسه را به‌صورت دستی کپی کنید.'); }}}>کپی شناسه</button></Dialog>}
    {notice&&<div className="live-notice" role="status"><Check size={17}/>{notice}<button onClick={()=>setNotice('')} aria-label="بستن"><X size={15}/></button></div>}
  </main>;
}

function Toolbar({ query, setQuery, placeholder, action, actionLabel }) {
  return <div className="live-toolbar"><label className="live-search"><Search size={17}/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder={placeholder}/></label>{action&&<button className="live-primary" onClick={action}><Plus size={16}/>{actionLabel}</button>}</div>;
}

function DeviceTable({ devices, canEdit, onSelect, onEdit, onArchive, onProvision, filtered }) {
  if (!devices.length) return <Empty text={filtered ? 'دستگاهی با این فیلترها یافت نشد.' : 'دستگاهی ثبت نشده است.'}/>;
  return <div className="live-table-wrap"><table className="live-table"><thead><tr><th>سریال</th><th>مدل</th><th>مشتری</th><th>وضعیت</th><th>آخرین ارتباط</th><th>نسخه</th><th>خطای فعال</th><RecordHistoryHeaders archive/>{canEdit&&<th>عملیات</th>}</tr></thead><tbody>{devices.map(device=><tr key={device.id}><td><button className="live-link" dir="ltr" onClick={()=>onSelect(device)}>{device.serial_number}</button></td><td>{device.model_display_name || device.model_name}{device.model_display_name && <small dir="ltr">{device.model_name}</small>}</td><td>{device.customer_name}</td><td>{device.is_archived&&<ArchiveBadge/>}<Status value={device.is_online?'online':'offline'}/></td><td>{formatDate(device.last_seen_at)}</td><td dir="ltr">{device.software_version||'—'}</td><td>{device.active_fault_count||0}</td><RecordHistoryCells record={device} archive/>{canEdit&&<td className="live-row-actions">{!device.is_archived&&<><RowAction action="edit" label="ویرایش" onClick={()=>onEdit(device)}/><RowAction action="credential" label="شناسه" onClick={()=>onProvision?.(device)}/><RowAction action="archive" label="بایگانی" danger onClick={()=>onArchive?.(device)}/></>}</td>}</tr>)}</tbody></table></div>;
}

function CustomerTable({ customers, canEdit, onEdit, onArchive, filtered }) {
  if (!customers.length) return <Empty text={filtered ? 'مشتری‌ای با این فیلترها یافت نشد.' : 'مشتری‌ای برای نمایش وجود ندارد.'}/>;
  return <div className="live-table-wrap"><table className="live-table"><thead><tr><th>سازمان</th><th>مسئول</th><th>ایمیل</th><th>تلفن</th><th>دستگاه‌ها</th><th>وضعیت</th><RecordHistoryHeaders archive/>{canEdit&&<th>عملیات</th>}</tr></thead><tbody>{customers.map(customer=><tr key={customer.id}><td>{customer.organization_name}</td><td>{customer.contact_name}</td><td dir="ltr">{customer.contact_email||'—'}</td><td dir="ltr">{customer.contact_phone||'—'}</td><td>{customer.device_count||0}</td><td>{customer.is_archived?'بایگانی‌شده':'فعال'}</td><RecordHistoryCells record={customer} archive/>{canEdit&&<td className="live-row-actions">{!customer.is_archived&&<><RowAction action="edit" label="ویرایش" onClick={()=>onEdit(customer)}/><RowAction action="archive" label="بایگانی" danger onClick={()=>onArchive(customer)}/></>}</td>}</tr>)}</tbody></table></div>;
}

function ReleaseTable({ releases, assignments, isAdmin, onWithdraw, onRollback }) {
  if (!releases.length) return <Empty text="نسخه‌ای ثبت نشده است."/>;
  return <div className="live-table-wrap"><table className="live-table"><thead><tr><th>نسخه</th><th>وضعیت</th><th>سازگاری</th><th>انتشار</th><th>نتیجهٔ دستگاه‌ها</th><RecordHistoryHeaders withdrawal/>{isAdmin&&<th>عملیات</th>}</tr></thead><tbody>{releases.map(release=>{const outcomes=assignments.filter(item=>item.release===release.id);return <tr key={release.id}><td dir="ltr">{release.version}</td><td><Status value={release.status}/></td><td>{release.compatible_models?.length?release.compatible_models.join('، '):'همهٔ مدل‌ها'}</td><td>{formatDate(release.published_at)}</td><td>{outcomes.length?outcomes.map(item=>`${item.device_serial}: ${labels[item.state]||item.state}`).join(' · '):'در انتظار گزارش'}</td><RecordHistoryCells record={release} withdrawal/>{isAdmin&&<td className="live-row-actions">{release.status==='published'&&<RowAction action="withdraw" label="پس‌گرفتن" danger onClick={()=>onWithdraw(release)}/>}{release.status==='published'&&<RowAction action="rollback" label="تخصیص بازگشت" onClick={()=>onRollback(release)}/>}</td>}</tr>;})}</tbody></table></div>;
}

