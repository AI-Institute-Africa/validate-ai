import { useState, type FormEvent } from "react";
import { Dialog } from "./Dialog";
import "./actionDialog.css";

type ConfirmDialogProps = {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
};

/** Touch/keyboard replacement for window.confirm, with a visible Cancel path. */
export function ConfirmDialog({ title, message, confirmLabel, danger, onConfirm, onClose }: ConfirmDialogProps) {
  return (
    <Dialog title={title} onClose={onClose}>
      <p className="ad-message">{message}</p>
      <div className="dialog-actions">
        <button type="button" className="ghost" onClick={onClose}>Cancel</button>
        <button type="button" className={danger ? "danger" : ""} onClick={() => { onClose(); onConfirm(); }}>
          {confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}

type ReasonDialogProps = {
  title: string;
  label: string;
  message?: string;
  placeholder?: string;
  confirmLabel: string;
  minLength?: number;
  optional?: boolean;
  danger?: boolean;
  onConfirm: (reason: string) => void;
  onClose: () => void;
};

/** Touch/keyboard replacement for window.prompt: labelled input, visible validation and Cancel. */
export function ReasonDialog({
  title,
  label,
  message,
  placeholder,
  confirmLabel,
  minLength = 3,
  optional = false,
  danger,
  onConfirm,
  onClose,
}: ReasonDialogProps) {
  const [reason, setReason] = useState("");
  const valid = optional || reason.trim().length >= minLength;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) {
      onClose();
      onConfirm(reason.trim());
    }
  };
  return (
    <Dialog title={title} onClose={onClose}>
      <form onSubmit={submit}>
        {message && <p className="ad-message">{message}</p>}
        <label className="ad-field">
          {label}
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={placeholder} autoFocus />
          <span className="ad-hint">
            {optional ? "Optional" : `At least ${minLength} characters, kept in the audit trail.`}
          </span>
        </label>
        <div className="dialog-actions">
          <button type="button" className="ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className={danger ? "danger" : ""} disabled={!valid}>{confirmLabel}</button>
        </div>
      </form>
    </Dialog>
  );
}
