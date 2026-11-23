import React, { useId, useLayoutEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { shellText } from './locale.js';

export default function Dialog({ title, onClose, children, dismissible = true, className = '' }) {
  const dialog = useRef(null);
  const titleId = useId();
  const close = useRef(onClose);
  close.current = onClose;

  useLayoutEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    element.showModal();
    return () => {
      element.close();
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
    };
  }, []);

  function dismiss(event) {
    event.preventDefault();
    if (dismissible) close.current();
  }

  function backdrop(event) {
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.target === event.currentTarget && (
      event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom
    )) dismiss(event);
  }

  function keepFocus(event) {
    if (event.key !== 'Tab') return;
    const items = [...event.currentTarget.querySelectorAll(
      'button, input:not([type="hidden"]), select, textarea, a[href], [tabindex]:not([tabindex="-1"])',
    )].filter(element => !element.disabled && element.getClientRects().length > 0);
    const first = items[0];
    const last = items.at(-1);
    if (!first) { event.preventDefault(); return; }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first.focus();
    }
  }

  return createPortal(<dialog ref={dialog} className={`live-modal live-dialog ${className}`} dir="rtl"
    aria-labelledby={titleId} onCancel={dismiss} onClick={backdrop} onKeyDown={keepFocus}>
    <header><h2 id={titleId}>{title}</h2><button type="button" onClick={dismiss} disabled={!dismissible} aria-label={shellText.close}><X/></button></header>
    {children}
  </dialog>, document.body);
}
