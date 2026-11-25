import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { CalendarDate, getDayOfWeek } from '@internationalized/date';
import { currentPersianDate, months, parsePersianDateTime, persianCalendar, persianDigits, pickerDate, selectedDateText } from './dates.js';
import './persian-calendar.css';

export default function PersianDateTimePicker({ label, value, onChange }) {
  const id = useId();
  const root = useRef(null);
  const toggle = useRef(null);
  const popup = useRef(null);
  const focusDay = useRef(false);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 8, top: 8, width: 304 });
  const [focused, setFocused] = useState(currentPersianDate);
  const first = new CalendarDate(persianCalendar, focused.year, focused.month, 1);
  const offset = getDayOfWeek(first, 'fa-IR');
  const days = persianCalendar.getDaysInMonth(first);
  let selected = null;
  try { if (value) selected = parsePersianDateTime(value); } catch { /* Invalid text must not highlight a different date. */ }
  const heading = `${months[focused.month - 1]} ${persianDigits(focused.year)}`;

  useLayoutEffect(() => {
    if (!open) return;
    function place() {
      const pane = popup.current;
      const anchor = toggle.current;
      if (!pane || !anchor) return;
      const viewport = window.visualViewport;
      const leftEdge = (viewport?.offsetLeft || 0) + 8;
      const topEdge = (viewport?.offsetTop || 0) + 8;
      const availableWidth = (viewport?.width || window.innerWidth) - 16;
      const maxHeight = Math.max(80, (viewport?.height || window.innerHeight) - 16);
      const width = Math.min(304, availableWidth);
      const height = Math.min(pane.scrollHeight + 2, maxHeight);
      const rect = anchor.getBoundingClientRect();
      let top = rect.bottom + 6;
      if (top + height > topEdge + maxHeight) top = rect.top - height - 6;
      top = Math.max(topEdge, Math.min(top, topEdge + maxHeight - height));
      const left = Math.max(leftEdge, Math.min(rect.right - width, leftEdge + availableWidth - width));
      setPosition({ left, top, width, maxHeight });
    }
    const scroll = event => { if (!popup.current?.contains(event.target)) place(); };
    place();
    window.addEventListener('scroll', scroll, true);
    window.visualViewport?.addEventListener('resize', place);
    window.visualViewport?.addEventListener('scroll', place);
    return () => {
      window.removeEventListener('scroll', scroll, true);
      window.visualViewport?.removeEventListener('resize', place);
      window.visualViewport?.removeEventListener('scroll', place);
    };
  }, [open, focused.year, focused.month]);

  useEffect(() => {
    if (open && focusDay.current) { root.current?.querySelector(`[data-day="${focused.day}"]`)?.focus({ preventScroll: true }); focusDay.current = false; }
  }, [open, focused]);
  useEffect(() => {
    if (!open) return;
    const outside = event => { if (!root.current?.contains(event.target)) setOpen(false); };
    const resize = () => setOpen(false);
    const escape = event => { if (event.key === 'Escape') { event.stopPropagation(); setOpen(false); toggle.current?.focus(); } };
    document.addEventListener('pointerdown', outside);
    window.addEventListener('resize', resize);
    root.current?.addEventListener('keydown', escape);
    const element = root.current;
    return () => { document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', resize); element?.removeEventListener('keydown', escape); };
  }, [open]);

  function choose(date) { onChange(selectedDateText(date, value)); setOpen(false); toggle.current?.focus(); }
  function move(event, date) {
    const changes = { ArrowRight: { days: -1 }, ArrowLeft: { days: 1 }, ArrowUp: { days: -7 }, ArrowDown: { days: 7 }, PageUp: { months: -1 }, PageDown: { months: 1 }, Home: { days: -getDayOfWeek(date, 'fa-IR') }, End: { days: 6 - getDayOfWeek(date, 'fa-IR') } };
    if (changes[event.key]) { event.preventDefault(); focusDay.current = true; setFocused(date.add(changes[event.key])); }
  }
  const cells = Array.from({ length: Math.ceil((offset + days) / 7) * 7 }, (_, index) => index - offset + 1);
  return <div className="live-field persian-date-field" ref={root}>
    <label htmlFor={id}>{label}</label><div className="persian-date-input"><input id={id} value={value} onChange={event => onChange(event.target.value)} dir="ltr" placeholder="۱۴۰۴/۰۱/۰۱ ۱۲:۳۰:۰۰" aria-describedby={`${id}-hint`} autoComplete="off"/><button ref={toggle} type="button" aria-label={`انتخاب تاریخ ${label}`} aria-expanded={open} aria-controls={`${id}-calendar`} onClick={() => { if (!open) { setFocused(pickerDate(value)); focusDay.current = true; } setOpen(!open); }}><CalendarDays size={19}/></button></div>
    <small id={`${id}-hint`}>شمسی · ساعت تهران · ساعت:دقیقه:ثانیه</small>
    {open && <section ref={popup} id={`${id}-calendar`} className="persian-calendar" style={position} aria-label={`تقویم شمسی ${label}`}>
      <div className="persian-calendar-heading"><button type="button" aria-label="ماه قبل" onClick={() => setFocused(first.subtract({ months: 1 }))}><ChevronRight size={18}/></button><b aria-live="polite">{heading}</b><button type="button" aria-label="ماه بعد" onClick={() => setFocused(first.add({ months: 1 }))}><ChevronLeft size={18}/></button></div>
      <div className="persian-calendar-selects"><label>ماه<select aria-label="ماه تقویم" value={focused.month} onChange={event => setFocused(first.set({ month: Number(event.target.value) }))}>{months.map((month, index) => <option value={index + 1} key={month}>{month}</option>)}</select></label><label>سال<select aria-label="سال تقویم" value={focused.year} onChange={event => setFocused(first.set({ year: Number(event.target.value) }))}>{Array.from({ length: 121 }, (_, i) => focused.year - 100 + i).filter(year => year > 0).map(year => <option key={year} value={year}>{persianDigits(year)}</option>)}</select></label></div>
      <table role="grid" aria-label={heading}><thead><tr>{['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'].map((day, index) => <th key={index} scope="col">{day}</th>)}</tr></thead><tbody>{Array.from({ length: cells.length / 7 }, (_, week) => <tr key={week}>{cells.slice(week * 7, week * 7 + 7).map((day, index) => <td key={index}>{day > 0 && day <= days && <button type="button" data-day={day} tabIndex={day === focused.day ? 0 : -1} aria-label={`${persianDigits(day)} ${heading}`} aria-pressed={Boolean(selected && selected.year === first.year && selected.month === first.month && selected.day === day)} onFocus={() => setFocused(first.set({ day }))} onKeyDown={event => move(event, first.set({ day }))} onClick={() => choose(first.set({ day }))}>{persianDigits(day)}</button>}</td>)}</tr>)}</tbody></table>
      <footer><button type="button" onClick={() => choose(currentPersianDate())}>امروز</button><button type="button" onClick={() => { setOpen(false); toggle.current?.focus(); }}>بستن تقویم</button></footer>
    </section>}
  </div>;
}
