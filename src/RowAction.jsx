import React from 'react';
import { Archive, KeyRound, Pencil, Power, RotateCcw, Undo2 } from 'lucide-react';
import './row-action.css';

const icons = { edit: Pencil, archive: Archive, credential: KeyRound, toggle: Power, withdraw: Undo2, rollback: RotateCcw };

export default function RowAction({ action, label, danger = false, ...props }) {
  const Icon = icons[action];
  return <button {...props} type="button" className={`row-action${danger ? ' row-action-danger' : ''}`} aria-label={label} title={label}><Icon size={18} aria-hidden="true"/></button>;
}
