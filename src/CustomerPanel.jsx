import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Cpu, LogOut, Menu, Moon, RefreshCw, Search, Sun } from 'lucide-react';
import { api } from './api.js';
import Dialog from './Dialog.jsx';
import { formatDate } from './EventTable.jsx';
import { customerText as t, shellText } from './locale.js';

const listPath = '/customer/devices';
function deviceId() {
  return window.location.pathname.match(/^\/customer\/devices\/(\d+)\/?$/)?.[1] || '';
}

function Connection({ device }) {
  return <span className={`live-status ${device.is_online ? 'good' : ''}`}>{!device.last_seen_at ? t.never : device.is_online ? t.online : t.offline}</span>;
}

export default function CustomerPanel({ organization, email, theme, onTheme, onLogout, onSessionExpired, parentError }) {
  const [id, setId] = useState(deviceId);
  const [query, setQuery] = useState('');
  const [online, setOnline] = useState('');
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [summary, setSummary] = useState(null);
  const [payload, setPayload] = useState(null);
  const [device, setDevice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState('');
  const [missing, setMissing] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const heading = useRef(null);
  const revision = useRef(0);

  const clear = useCallback(() => { revision.current += 1; setSummary(null); setPayload(null); setDevice(null); setLoading(true); }, []);
  const navigate = useCallback((next = '') => {
    clear(); setMissing(false); setError(''); setDrawer(false);
    window.history.pushState(null, '', next ? `${listPath}/${next}` : listPath);
    setId(next); setPage(1); setRefresh(value => value + 1);
  }, [clear]);

  useEffect(() => {
    if (!window.location.pathname.match(/^\/customer\/devices(?:\/\d+)?\/?$/)) {
      window.history.replaceState(null, '', listPath);
    }
    const pop = () => {
      clear(); setId(deviceId()); setRefresh(value => value + 1);
      if (!window.location.pathname.startsWith(listPath)) window.history.replaceState(null, '', listPath);
    };
    window.addEventListener('popstate', pop);
    return () => window.removeEventListener('popstate', pop);
  }, [clear]);

  useEffect(() => { heading.current?.focus(); }, [id]);

  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    clear(); setError(''); setMissing(false);
    const requestRevision = revision.current;
    Promise.all([
      api.session(options), api.customerSummary(options),
      id ? api.customerDevice(id, options) : api.customerDevices({ page, search: query, ...(online ? { online } : {}) }, options),
    ]).then(([session, nextSummary, nextData]) => {
      if (controller.signal.aborted || requestRevision !== revision.current) return;
      if (session.role !== 'customer' || session.organization?.id !== organization?.id) {
        onSessionExpired(); return;
      }
      setSummary(nextSummary);
      if (id) setDevice(nextData); else setPayload(nextData);
    }).catch(cause => {
      if (controller.signal.aborted || requestRevision !== revision.current) return;
      // Promise.all fails closed: don't retain earlier records or late results.
      if (cause.status === 401 || cause.status === 403) onSessionExpired();
      else if (cause.status === 404 && id) setMissing(true);
      else setError(t.error);
    }).finally(() => { if (!controller.signal.aborted && requestRevision === revision.current) setLoading(false); });
    return () => { revision.current += 1; controller.abort(); };
  }, [id, query, online, page, refresh, organization?.id, onSessionExpired, clear]);

  useEffect(() => {
    const revalidate = () => {
      if (document.visibilityState === 'visible') { clear(); setRefresh(value => value + 1); }
    };
    const timer = setInterval(revalidate, 60000);
    window.addEventListener('focus', revalidate);
    window.addEventListener('pageshow', revalidate);
    document.addEventListener('visibilitychange', revalidate);
    return () => {
      clearInterval(timer); window.removeEventListener('focus', revalidate); window.removeEventListener('pageshow', revalidate);
      document.removeEventListener('visibilitychange', revalidate);
    };
  }, [clear]);

  const navigation = <nav aria-label={shellText.navigation}><button className="selected" aria-current="page" onClick={() => navigate()}><Cpu size={18}/>{t.title}</button></nav>;
  const stale = summary && Date.now() - new Date(summary.generated_at).getTime() > 90000;
  return <main className="live-app customer-panel" dir="rtl">
    <a className="live-skip" href="#customer-content">{shellText.skipNavigation}</a>
    <aside className="live-sidebar"><div className="live-brand"><Cpu/><div><b>پیشگامان شرق</b><span>{t.panel}</span></div></div>{navigation}<div className="live-sidebar-foot"><span>{organization?.name}</span><span dir="ltr">{email}</span></div></aside>
    <section className="live-main" id="customer-content" tabIndex={-1}>
      <header className="live-top"><div><h1 ref={heading} tabIndex={-1}>{id ? t.detail : t.title}</h1><p>{organization?.name}</p><p>{loading ? t.loading : `${t.updated}: ${formatDate(summary?.generated_at)}`}</p></div><div className="live-actions">
        <button className="live-icon live-menu-toggle" aria-label={shellText.openNavigation} aria-haspopup="dialog" aria-expanded={drawer} onClick={() => setDrawer(true)}><Menu size={18}/></button>
        <button className="live-icon" aria-label={t.theme} onClick={onTheme}>{theme === 'dark' ? <Sun size={18}/> : <Moon size={18}/>}</button>
        <button className="live-icon" aria-label={t.refresh} disabled={loading} onClick={() => { clear(); setRefresh(value => value + 1); }}><RefreshCw size={18}/></button>
        <button className="live-secondary" disabled={leaving} onClick={async () => { setLeaving(true); try { await onLogout(); } finally { setLeaving(false); } }}><LogOut size={16}/>{t.logout}</button>
      </div></header>
      {parentError && <p role="alert" className="live-error">{parentError}</p>}
      {error && <p role="alert" className="live-error">{error}</p>}
      {stale && <p role="status" className="live-hint">{t.stale}</p>}
      {!id && summary && <section className="live-metrics customer-metrics" aria-label={t.organization}>{[['device_count', t.total], ['online_count', t.online], ['offline_count', t.offline]].map(([key, title]) => <article key={key}><span>{title}</span><b>{Number(summary[key]).toLocaleString('fa-IR')}</b></article>)}</section>}
      {!id && <section className="live-card">
        <div className="live-toolbar"><label className="live-search"><Search size={17}/><input aria-label={t.search} placeholder={t.search} value={query} onChange={e => { clear(); setQuery(e.target.value); setPage(1); }}/></label><label className="live-field"><span>{t.filter}</span><select value={online} onChange={e => { clear(); setOnline(e.target.value); setPage(1); }}><option value="">{t.all}</option><option value="true">{t.online}</option><option value="false">{t.offline}</option></select></label></div>
        {loading && <p role="status">{t.loading}</p>}
        {!loading && !error && payload && <>{payload.results.length ? <div className="live-table-wrap"><table className="live-table"><thead><tr><th>{t.serial}</th><th>{t.model}</th><th>{t.connection}</th><th>{t.lastSeen}</th><th>{t.version}</th></tr></thead><tbody>{payload.results.map(item => <tr key={item.id}><td><a dir="ltr" href={`${listPath}/${item.id}`} onClick={e => { if (!e.ctrlKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); navigate(String(item.id)); } }}>{item.serial_number}</a></td><td>{item.model_name}</td><td><Connection device={item}/></td><td>{item.last_seen_at ? formatDate(item.last_seen_at) : t.never}</td><td dir="ltr">{item.software_version || '—'}</td></tr>)}</tbody></table></div> : <div className="live-empty"><p>{query || online ? t.noMatches : t.empty}</p>{(query || online) && <button className="live-secondary" onClick={() => { clear(); setQuery(''); setOnline(''); setPage(1); }}>{t.clear}</button>}</div>}
          <div className="live-staff-pagination"><button className="live-secondary" disabled={!payload.previous} onClick={() => { clear(); setPage(value => value - 1); }}>{t.previous}</button><span>{t.page} {page.toLocaleString('fa-IR')} · {Number(payload.count).toLocaleString('fa-IR')}</span><button className="live-secondary" disabled={!payload.next} onClick={() => { clear(); setPage(value => value + 1); }}>{t.next}</button></div></>}
      </section>}
      {id && <section className="live-card"><button className="live-secondary" onClick={() => navigate()}>{t.back}</button>{loading && <p role="status">{t.loading}</p>}{missing && <p role="alert">{t.unavailable}</p>}{device && <><h2 dir="ltr">{device.serial_number}</h2><dl className="live-detail"><dt>{t.model}</dt><dd>{device.model_name}</dd><dt>{t.version}</dt><dd dir="ltr">{device.software_version || '—'}</dd><dt>{t.location}</dt><dd>{device.location || '—'}</dd><dt>{t.lastSeen}</dt><dd>{device.last_seen_at ? formatDate(device.last_seen_at) : t.never}</dd><dt>{t.connection}</dt><dd><Connection device={device}/></dd></dl></>}</section>}
      <footer className="live-footer">{t.estimate} {summary ? summary.online_window_minutes.toLocaleString('fa-IR') : '…'} {t.minutes} {t.safety}</footer>
    </section>
    {drawer && <Dialog title={shellText.navigation} className="live-drawer" onClose={() => setDrawer(false)}>{navigation}</Dialog>}
  </main>;
}
