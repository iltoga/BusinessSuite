export function unwrapApiEnvelope<T = unknown>(value: unknown): T | unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return value;
  }

  const envelope = value as { data?: unknown };
  if ('data' in envelope && envelope.data !== undefined) {
    return envelope.data as T;
  }

  return value;
}

export function unwrapApiRecord(value: unknown): Record<string, unknown> | null {
  const unwrapped = unwrapApiEnvelope(value);
  if (!unwrapped || typeof unwrapped !== 'object' || Array.isArray(unwrapped)) {
    return null;
  }
  return unwrapped as Record<string, unknown>;
}
