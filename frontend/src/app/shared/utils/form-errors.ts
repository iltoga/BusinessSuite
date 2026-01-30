import { FormArray, FormGroup, type AbstractControl } from '@angular/forms';

type ErrorPayload = Record<string, unknown> | undefined | null;

type ErrorItem = {
  path: string;
  label: string;
  message: string;
};

const toCamelCase = (value: string) =>
  value.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());

const normalizeErrorPayload = (errorResponse: unknown): ErrorPayload => {
  if (!errorResponse || typeof errorResponse !== 'object') return null;
  const payload = (errorResponse as any).error ?? errorResponse;
  if (!payload || typeof payload !== 'object') return null;

  const payloadErrors = (payload as any).errors;
  if (payloadErrors && typeof payloadErrors === 'object') {
    if (typeof (payloadErrors as any).errors === 'object') {
      return (payloadErrors as any).errors as Record<string, unknown>;
    }
    return payloadErrors as Record<string, unknown>;
  }

  const details = (payload as any).details;
  if (details && typeof details === 'object') {
    if (typeof (details as any).errors === 'object') {
      return (details as any).errors as Record<string, unknown>;
    }
    if (Array.isArray((details as any).errors)) {
      return { nonFieldErrors: (details as any).errors } as Record<string, unknown>;
    }
    return details as Record<string, unknown>;
  }

  return payload as Record<string, unknown>;
};

const setServerError = (control: AbstractControl, message: string) => {
  const current = control.errors ?? {};
  control.setErrors({ ...current, server: message });
};

const extractMessage = (value: unknown): string | null => {
  if (!value) return null;
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    const list = value.filter((item) => typeof item === 'string') as string[];
    return list.length ? list.join(' ') : null;
  }
  return null;
};

const applyErrorsToControl = (control: AbstractControl, value: unknown) => {
  const message = extractMessage(value);
  if (message) {
    setServerError(control, message);
  }
};

const applyErrorsToArray = (arrayControl: FormArray, value: unknown) => {
  if (!Array.isArray(value)) return;
  value.forEach((entry, index) => {
    const row = arrayControl.at(index);
    if (!row) return;
    if (entry && typeof entry === 'object') {
      applyErrorsToGroup(row as FormGroup, entry as Record<string, unknown>);
    } else {
      const message = extractMessage(entry);
      if (message) {
        setServerError(row, message);
      }
    }
  });
};

const applyErrorsToGroup = (group: FormGroup, errors: Record<string, unknown>) => {
  for (const [key, value] of Object.entries(errors)) {
    const normalizedKey = toCamelCase(key);
    if (normalizedKey === 'nonFieldErrors' || normalizedKey === 'detail') {
      const message = extractMessage(value);
      if (message) {
        setServerError(group, message);
      }
      continue;
    }

    const control = group.get(normalizedKey) ?? group.get(key);
    if (!control) {
      const message = extractMessage(value);
      if (message) {
        setServerError(group, message);
      }
      continue;
    }

    if (control instanceof FormArray) {
      applyErrorsToArray(control, value);
      const arrayMessage = extractMessage(value);
      if (arrayMessage) {
        setServerError(control, arrayMessage);
      }
      continue;
    }

    if (value && typeof value === 'object' && !Array.isArray(value)) {
      if (control instanceof FormGroup) {
        applyErrorsToGroup(control, value as Record<string, unknown>);
      } else {
        const message = extractMessage(value);
        if (message) {
          setServerError(control, message);
        }
      }
      continue;
    }

    applyErrorsToControl(control, value);
  }
};

export const applyServerErrorsToForm = (form: AbstractControl, errorResponse: unknown) => {
  const errors = normalizeErrorPayload(errorResponse);
  if (!errors || typeof errors !== 'object') return;

  if (form instanceof FormGroup) {
    applyErrorsToGroup(form, errors as Record<string, unknown>);
  } else if (form instanceof FormArray) {
    applyErrorsToArray(form, errors);
  } else {
    const message = extractMessage(errors);
    if (message) {
      setServerError(form, message);
    }
  }
};

const formatLabel = (path: string, labels: Record<string, string>) => {
  if (labels[path]) return labels[path];
  return path
    .replace(/\[(\d+)\]/g, ' #$1')
    .replace(/\./g, ' ')
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (m) => m.toUpperCase());
};

export const collectServerErrors = (
  control: AbstractControl,
  labels: Record<string, string> = {},
  path = '',
): ErrorItem[] => {
  const errors: ErrorItem[] = [];

  const serverMessage = control.errors?.['server'];
  if (serverMessage) {
    errors.push({
      path,
      label: formatLabel(path || 'Form', labels),
      message: String(serverMessage),
    });
  }

  if (control instanceof FormGroup) {
    for (const [key, child] of Object.entries(control.controls)) {
      const nextPath = path ? `${path}.${key}` : key;
      errors.push(...collectServerErrors(child, labels, nextPath));
    }
  }

  if (control instanceof FormArray) {
    control.controls.forEach((child, index) => {
      const nextPath = `${path}[${index + 1}]`;
      errors.push(...collectServerErrors(child, labels, nextPath));
    });
  }

  return errors;
};

export const extractServerErrorMessage = (errorResponse: unknown): string | null => {
  if (!errorResponse || typeof errorResponse !== 'object') return null;
  const payload = (errorResponse as any).error ?? errorResponse;
  if (!payload || typeof payload !== 'object') return null;

  const direct = (payload as any).error;
  const detail = (payload as any).detail;
  const errorsRoot = (payload as any).errors;
  const details = (payload as any).details;

  if (Array.isArray(details?.errors) && details.errors.length > 0) {
    return String(details.errors.join(' '));
  }

  if (errorsRoot && typeof errorsRoot === 'object') {
    const inner =
      (errorsRoot as any).errors && typeof (errorsRoot as any).errors === 'object'
        ? (errorsRoot as any).errors
        : errorsRoot;
    for (const [key, value] of Object.entries(inner)) {
      if (key === 'code') continue;
      const message = extractMessage(value);
      if (message) return message;
    }
  }

  if (typeof detail === 'string') return detail;

  if (typeof direct === 'string') return direct;

  return null;
};
