import { FormArray, FormGroup, type AbstractControl } from '@angular/forms';

type ErrorPayload = Record<string, unknown> | undefined | null;

type ErrorItem = {
  path: string;
  label: string;
  message: string;
};

const toCamelCase = (value: string) =>
  value.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());

const unwrapErrorPayload = (errorResponse: unknown): Record<string, unknown> | null => {
  if (!errorResponse || typeof errorResponse !== 'object') return null;
  const payload = (errorResponse as any).error ?? errorResponse;
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  return payload as Record<string, unknown>;
};

const getCanonicalErrorObject = (payload: Record<string, unknown>): Record<string, unknown> | null => {
  const canonical = payload['error'];
  if (!canonical || typeof canonical !== 'object' || Array.isArray(canonical)) {
    return null;
  }
  return canonical as Record<string, unknown>;
};

const normalizeErrorPayload = (errorResponse: unknown): ErrorPayload => {
  const payload = unwrapErrorPayload(errorResponse);
  if (!payload || typeof payload !== 'object') return null;

  const canonicalError = getCanonicalErrorObject(payload);
  if (canonicalError) {
    const canonicalDetails = canonicalError['details'] ?? canonicalError['errors'];
    if (Array.isArray(canonicalDetails)) {
      return { nonFieldErrors: canonicalDetails } as Record<string, unknown>;
    }
    if (canonicalDetails && typeof canonicalDetails === 'object') {
      const canonicalDetailsRecord = canonicalDetails as Record<string, unknown>;
      if (typeof canonicalDetailsRecord['errors'] === 'object') {
        return canonicalDetailsRecord['errors'] as Record<string, unknown>;
      }
      if (Array.isArray(canonicalDetailsRecord['errors'])) {
        return { nonFieldErrors: canonicalDetailsRecord['errors'] } as Record<string, unknown>;
      }
      return canonicalDetails as Record<string, unknown>;
    }
    const canonicalMessage = extractMessage(canonicalError['message'] ?? canonicalError['detail']);
    if (canonicalMessage) {
      return { nonFieldErrors: [canonicalMessage] } as Record<string, unknown>;
    }
  }

  const payloadErrors = payload['errors'];
  if (Array.isArray(payloadErrors)) {
    return { nonFieldErrors: payloadErrors } as Record<string, unknown>;
  }
  if (payloadErrors && typeof payloadErrors === 'object') {
    const payloadErrorsRecord = payloadErrors as Record<string, unknown>;
    if (typeof payloadErrorsRecord['errors'] === 'object') {
      return payloadErrorsRecord['errors'] as Record<string, unknown>;
    }
    return payloadErrors as Record<string, unknown>;
  }

  const details = payload['details'];
  if (Array.isArray(details)) {
    return { nonFieldErrors: details } as Record<string, unknown>;
  }
  if (details && typeof details === 'object') {
    const detailsRecord = details as Record<string, unknown>;
    if (typeof detailsRecord['errors'] === 'object') {
      return detailsRecord['errors'] as Record<string, unknown>;
    }
    if (Array.isArray(detailsRecord['errors'])) {
      return { nonFieldErrors: detailsRecord['errors'] } as Record<string, unknown>;
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

const extractFirstStringFromObject = (value: unknown): string | null => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }

  for (const entry of Object.values(value as Record<string, unknown>)) {
    const message = extractMessage(entry);
    if (message) {
      return message;
    }
    const nested = extractFirstStringFromObject(entry);
    if (nested) {
      return nested;
    }
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
  const payload = unwrapErrorPayload(errorResponse);
  if (!payload || typeof payload !== 'object') return null;

  const canonicalError = getCanonicalErrorObject(payload);
  if (canonicalError) {
    const canonicalMessage = extractMessage(canonicalError['message'] ?? canonicalError['detail']);
    if (canonicalMessage) {
      return canonicalMessage;
    }

    const canonicalDetails = canonicalError['details'] ?? canonicalError['errors'];
    const canonicalDetailsMessage = extractMessage(canonicalDetails);
    if (canonicalDetailsMessage) {
      return canonicalDetailsMessage;
    }

    const canonicalDetailsObjectMessage = extractFirstStringFromObject(canonicalDetails);
    if (canonicalDetailsObjectMessage) {
      return canonicalDetailsObjectMessage;
    }
  }

  const direct = payload['error'];
  const detail = payload['detail'];
  const errorsRoot = payload['errors'];
  const details = payload['details'];

  if (typeof payload['message'] === 'string') return String(payload['message']);

  if (Array.isArray(details) && details.length > 0) {
    return details.map((item) => String(item)).join(' ');
  }

  if (details && typeof details === 'object') {
    const detailsRecord = details as Record<string, unknown>;
    if (Array.isArray(detailsRecord['errors']) && detailsRecord['errors'].length > 0) {
      return String(detailsRecord['errors'].join(' '));
    }
  }

  if (errorsRoot && typeof errorsRoot === 'object') {
    const errorsRootRecord = errorsRoot as Record<string, unknown>;
    const inner =
      errorsRootRecord['errors'] && typeof errorsRootRecord['errors'] === 'object'
        ? errorsRootRecord['errors']
        : errorsRoot;
    for (const [key, value] of Object.entries(inner)) {
      if (key === 'code') continue;
      const message = extractMessage(value);
      if (message) return message;
    }
  }

  if (details && typeof details === 'object') {
    const message = extractFirstStringFromObject(details);
    if (message) return message;
  }

  if (typeof detail === 'string') return detail;

  if (typeof direct === 'string') return direct;

  return null;
};
