import { type AsyncJob } from '@/core/api';

export function firstDefined<T>(...values: Array<T | null | undefined>): T | undefined {
  return values.find((value): value is T => value !== undefined && value !== null);
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function toOptionalString(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : undefined;
  }

  if (typeof value === 'number' || typeof value === 'bigint' || typeof value === 'boolean') {
    return String(value);
  }

  return undefined;
}

export function toOptionalNumber(value: unknown): number | undefined {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : undefined;
  }

  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  return undefined;
}

function extractJobIdFromRecord(
  record: Record<string, unknown>,
  allowLegacyAlias = false,
): string | undefined {
  return firstDefined(
    toOptionalString(record['jobId']),
    allowLegacyAlias ? toOptionalString(record['job_id']) : undefined,
    toOptionalString(record['id']),
  );
}

function extractNestedRecord(record: Record<string, unknown>): Record<string, unknown> | null {
  const nestedPayload = record['payload'];
  if (isRecord(nestedPayload)) {
    return nestedPayload;
  }

  const nestedData = record['data'];
  if (isRecord(nestedData)) {
    return nestedData;
  }

  return null;
}

function extractPayloadRecord(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value)) {
    return null;
  }

  return extractNestedRecord(value);
}

export function extractJobId(value: unknown): string | undefined {
  if (!isRecord(value)) {
    return undefined;
  }

  return extractJobIdFromRecord(value) ?? extractJobIdFromRecord(extractNestedRecord(value) ?? {});
}

function extractLegacyJobId(value: unknown): string | undefined {
  if (!isRecord(value)) {
    return undefined;
  }

  return (
    extractJobIdFromRecord(value, true) ??
    extractJobIdFromRecord(extractNestedRecord(value) ?? {}, true)
  );
}

export function normalizeJobEnvelope<T extends object>(
  value: T,
): T & { jobId?: string } {
  const record = isRecord(value)
    ? (value as Record<string, unknown>)
    : ({} as Record<string, unknown>);
  const jobId = extractLegacyJobId(record);
  if (!jobId) {
    return value as T & { jobId?: string };
  }

  const { job_id: _legacyJobId, ...rest } = record;
  return {
    ...rest,
    jobId: toOptionalString(record['jobId']) ?? jobId,
  } as T & { jobId?: string };
}

export function normalizeAsyncJobUpdate(update: unknown): AsyncJob {
  const record = isRecord(update) ? update : {};
  const nested = extractPayloadRecord(record);
  const jobId = firstDefined(
    extractLegacyJobId(record),
    nested ? extractLegacyJobId(nested) : undefined,
  ) ?? '';
  const status = firstDefined(
    toOptionalString(record['status']),
    nested ? toOptionalString(nested['status']) : undefined,
  ) ?? '';
  const progress = firstDefined(
    toOptionalNumber(record['progress']),
    nested ? toOptionalNumber(nested['progress']) : undefined,
  ) ?? 0;

  const job: Record<string, unknown> = {
    id: jobId,
    status: status as AsyncJob.StatusEnum,
    progress,
  };

  const message = firstDefined(
    toOptionalString(record['message']),
    nested ? toOptionalString(nested['message']) : undefined,
  );
  if (message !== undefined) {
    job['message'] = message;
  }

  const result = firstDefined(record['result'], nested?.['result']);
  if (result !== undefined) {
    job['result'] = result;
  }

  const errorMessage = firstDefined(
    toOptionalString(record['errorMessage']),
    toOptionalString(record['error_message']),
    toOptionalString(record['error']),
    nested ? toOptionalString(nested['errorMessage']) : undefined,
    nested ? toOptionalString(nested['error_message']) : undefined,
    nested ? toOptionalString(nested['error']) : undefined,
  );
  if (errorMessage !== undefined) {
    job['errorMessage'] = errorMessage;
    job['error'] = errorMessage;
  }

  return job as AsyncJob;
}
