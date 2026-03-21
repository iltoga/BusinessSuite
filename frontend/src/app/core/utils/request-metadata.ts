import { HttpContext, HttpContextToken } from '@angular/common/http';

export interface RequestMetadata {
  requestId: string;
  idempotencyKey?: string | null;
}

export const REQUEST_METADATA_CONTEXT = new HttpContextToken<RequestMetadata | null>(() => null);

function createRandomToken(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}_${crypto.randomUUID()}`;
  }

  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function normalizeToken(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function createRequestId(): string {
  return createRandomToken('req');
}

export function createIdempotencyKey(): string {
  return createRandomToken('idem');
}

export function createRequestMetadata(includeIdempotencyKey = false): RequestMetadata {
  return {
    requestId: createRequestId(),
    idempotencyKey: includeIdempotencyKey ? createIdempotencyKey() : null,
  };
}

export function createAsyncRequestMetadata(): RequestMetadata {
  return createRequestMetadata(true);
}

export function requestMetadataContext(metadata?: RequestMetadata | null): HttpContext {
  return new HttpContext().set(REQUEST_METADATA_CONTEXT, metadata ?? createRequestMetadata());
}

export function requestMetadataHeaders(metadata?: RequestMetadata | null): Record<string, string> {
  const resolved = metadata ?? createRequestMetadata();
  const headers: Record<string, string> = {
    'X-Request-ID': normalizeToken(resolved.requestId) ?? createRequestId(),
  };

  const idempotencyKey = normalizeToken(resolved.idempotencyKey);
  if (idempotencyKey) {
    headers['Idempotency-Key'] = idempotencyKey;
  }

  return headers;
}
