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

function snakeToCamelKey(key: string): string {
  if (!key.includes('_')) {
    return key;
  }

  const parts = key.split('_').filter(Boolean);
  if (parts.length === 0) {
    return key;
  }

  const [head, ...tail] = parts;
  return tail.reduce(
    (acc, part) => `${acc}${part.slice(0, 1).toUpperCase()}${part.slice(1)}`,
    head,
  );
}

export function camelizePayload(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => camelizePayload(item));
  }

  if (!isRecord(value)) {
    return value;
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [snakeToCamelKey(key), camelizePayload(item)]),
  );
}

function extractJobIdFromRecord(
  record: Record<string, unknown>,
): string | undefined {
  return firstDefined(
    toOptionalString(record['jobId']),
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

  const record = camelizePayload(value);
  if (!isRecord(record)) {
    return undefined;
  }

  return extractJobIdFromRecord(record) ?? extractJobIdFromRecord(extractNestedRecord(record) ?? {});
}

export function normalizeJobEnvelope<T extends object>(
  value: T,
): T & { jobId?: string } {
  const record = isRecord(value)
    ? (camelizePayload(value) as Record<string, unknown>)
    : ({} as Record<string, unknown>);
  const jobId = extractJobIdFromRecord(record) ?? extractJobIdFromRecord(extractNestedRecord(record) ?? {});
  if (!jobId) {
    return record as T & { jobId?: string };
  }

  return {
    ...record,
    jobId: toOptionalString(record['jobId']) ?? jobId,
  } as T & { jobId?: string };
}

export function normalizeAsyncJobUpdate(update: unknown): AsyncJob {
  const record = isRecord(update) ? (camelizePayload(update) as Record<string, unknown>) : {};
  const nested = extractPayloadRecord(record);
  const jobId = firstDefined(
    extractJobIdFromRecord(record),
    nested ? extractJobIdFromRecord(nested) : undefined,
  ) ?? '';
  const status = firstDefined(
    toOptionalString(record['status']),
    nested ? toOptionalString(nested['status']) : undefined,
  ) ?? '';
  const progress = firstDefined(
    toOptionalNumber(record['progress']),
    nested ? toOptionalNumber(nested['progress']) : undefined,
  ) ?? 0;
  const taskName = firstDefined(
    toOptionalString(record['taskName']),
    nested ? toOptionalString(nested['taskName']) : undefined,
  ) ?? '';

  const job: Record<string, unknown> = {
    jobId,
    taskName,
    status: status as AsyncJob.StatusEnum,
    progress,
    message: firstDefined(
      toOptionalString(record['message']),
      nested ? toOptionalString(nested['message']) : undefined,
    ) ?? null,
    result: firstDefined(record['result'], nested?.['result']) ?? null,
    errorMessage: firstDefined(
      toOptionalString(record['errorMessage']),
      nested ? toOptionalString(nested['errorMessage']) : undefined,
    ) ?? null,
    createdAt: firstDefined(
      toOptionalString(record['createdAt']),
      nested ? toOptionalString(nested['createdAt']) : undefined,
    ) ?? '',
    updatedAt: firstDefined(
      toOptionalString(record['updatedAt']),
      nested ? toOptionalString(nested['updatedAt']) : undefined,
    ) ?? '',
    createdBy: firstDefined(
      toOptionalNumber(record['createdBy']),
      nested ? toOptionalNumber(nested['createdBy']) : undefined,
    ) ?? null,
  };

  return job as AsyncJob;
}
