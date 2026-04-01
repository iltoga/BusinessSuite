import { unwrapApiRecord } from '@/core/utils/api-envelope';

// ── Response interfaces ─────────────────────────────────────────────

export interface MediaDiagnosticResult {
  model: string;
  id: number;
  field: string;
  path: string;
  absPath: string;
  exists: boolean;
  url: string;
  fileLink?: string;
  discrepancy: boolean;
}

export interface ServerSettings {
  mediaRoot: string;
  mediaUrl: string;
  debug: boolean;
}

export interface CacheStatusResponse {
  enabled: boolean;
  version: number;
  message: string;
  cacheBackend?: string;
  cacheLocation?: string;
  globalEnabled?: boolean;
  userEnabled?: boolean;
}

export interface CacheHealthResponse {
  ok: boolean;
  message: string;
  checkedAt: string;
  cacheBackend: string;
  cacheLocation: string;
  redisConfigured: boolean;
  redisConnected: boolean | null;
  userCacheEnabled?: boolean;
  probeSkipped?: boolean;
  writeReadDeleteOk: boolean | null;
  probeLatencyMs: number;
  errors: string[];
}

export interface LocalResilienceSettingsResponse {
  enabled: boolean;
  encryptionRequired: boolean;
  desktopMode: 'localPrimary' | 'remotePrimary' | string;
  vaultEpoch: number;
  updatedAt?: string;
  updatedBy?: {
    id: number;
    username?: string | null;
    email?: string | null;
  } | null;
}

export interface UiSettingsResponse {
  useOverlayMenu: boolean;
  updatedAt?: string;
  updatedBy?: {
    id: number;
    username?: string | null;
    email?: string | null;
  } | null;
}

export interface ServerActionResponse {
  ok: boolean;
  message: string;
}

export interface MediaDiagnosticResponse {
  ok: boolean;
  message: string;
  results: MediaDiagnosticResult[];
  settings: ServerSettings | null;
}

export interface MediaRepairResponse {
  ok: boolean;
  message: string;
  repairs: string[];
}

export interface MediaCleanupFile {
  path: string;
  sizeBytes?: number;
}

export interface MediaCleanupResult {
  ok: boolean;
  message: string;
  dryRun: boolean;
  prefixes: string[];
  scannedFiles: number;
  referencedFiles: number;
  orphanedFiles: number;
  deletedFiles: number;
  totalOrphanBytes: number;
  files: MediaCleanupFile[];
  errors: string[];
  storageBackend?: string;
  storageProvider?: string;
}

export interface MediaCleanupResponse {
  ok: boolean;
  message: string;
  cleanup: MediaCleanupResult | null;
}

export interface VaultResetResponse extends ServerActionResponse {
  vaultEpoch?: number;
}

// ── Type coercion helpers ───────────────────────────────────────────

export function toRecord(value: unknown): Record<string, unknown> | null {
  return unwrapApiRecord(value);
}

export function toOptionalString(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  return value;
}

export function toOptionalNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : undefined;
  }
  return undefined;
}

// ── Normalizers ─────────────────────────────────────────────────────

export function normalizeLocalResilience(raw: unknown): LocalResilienceSettingsResponse {
  const source = toRecord(raw);
  return {
    enabled: Boolean(source?.['enabled']),
    encryptionRequired: Boolean(source?.['encryptionRequired'] ?? true),
    desktopMode: String(source?.['desktopMode'] ?? 'localPrimary'),
    vaultEpoch: Number(source?.['vaultEpoch'] ?? 1),
    updatedAt: toOptionalString(source?.['updatedAt']),
    updatedBy: toRecord(source?.['updatedBy']) as
      | LocalResilienceSettingsResponse['updatedBy']
      | null,
  };
}

export function normalizeUiSettings(raw: unknown): UiSettingsResponse {
  const source = toRecord(raw);
  return {
    useOverlayMenu: Boolean(source?.['useOverlayMenu'] ?? false),
    updatedAt: toOptionalString(source?.['updatedAt']),
    updatedBy: toRecord(source?.['updatedBy']) as UiSettingsResponse['updatedBy'] | null,
  };
}

export function normalizeCacheHealth(raw: unknown): CacheHealthResponse {
  const source = toRecord(raw);
  const redisConnectedRaw = source?.['redisConnected'];
  const writeReadDeleteRaw = source?.['writeReadDeleteOk'];
  return {
    ok: Boolean(source?.['ok']),
    message: String(source?.['message'] ?? 'Cache health check complete'),
    checkedAt: String(source?.['checkedAt'] ?? ''),
    cacheBackend: String(source?.['cacheBackend'] ?? ''),
    cacheLocation: String(source?.['cacheLocation'] ?? ''),
    redisConfigured: Boolean(source?.['redisConfigured'] ?? false),
    redisConnected:
      redisConnectedRaw === null || redisConnectedRaw === undefined
        ? null
        : Boolean(redisConnectedRaw),
    userCacheEnabled: source?.['userCacheEnabled'] as boolean | undefined,
    probeSkipped: source?.['probeSkipped'] as boolean | undefined,
    writeReadDeleteOk:
      writeReadDeleteRaw === null || writeReadDeleteRaw === undefined
        ? null
        : Boolean(writeReadDeleteRaw),
    probeLatencyMs: Number(source?.['probeLatencyMs'] ?? 0),
    errors: Array.isArray(source?.['errors'])
      ? (source?.['errors'] as unknown[]).map((e) => String(e))
      : [],
  };
}

export function normalizeCacheStatus(raw: unknown): CacheStatusResponse {
  const source = toRecord(raw);
  const globalEnabledRaw = source?.['globalEnabled'];
  const userEnabledRaw = source?.['userEnabled'];
  return {
    enabled: Boolean(source?.['enabled']),
    version: Number(source?.['version'] ?? 1),
    message: String(source?.['message'] ?? 'Cache status updated'),
    cacheBackend: String(source?.['cacheBackend'] ?? ''),
    cacheLocation: String(source?.['cacheLocation'] ?? ''),
    globalEnabled: globalEnabledRaw === undefined ? undefined : Boolean(globalEnabledRaw),
    userEnabled: userEnabledRaw === undefined ? undefined : Boolean(userEnabledRaw),
  };
}

export function normalizeServerActionResponse(raw: unknown): ServerActionResponse {
  const source = toRecord(raw);
  return {
    ok: Boolean(source?.['ok']),
    message: toOptionalString(source?.['message']) ?? '',
  };
}

export function normalizeVaultResetResponse(raw: unknown): VaultResetResponse {
  const source = toRecord(raw);
  return {
    ok: Boolean(source?.['ok']),
    message: toOptionalString(source?.['message']) ?? '',
    vaultEpoch: toOptionalNumber(source?.['vaultEpoch'] ?? source?.['vault_epoch']),
  };
}

export function normalizeMediaDiagnosticResponse(raw: unknown): MediaDiagnosticResponse {
  const source = toRecord(raw);
  return {
    ok: Boolean(source?.['ok']),
    message: toOptionalString(source?.['message']) ?? '',
    results: Array.isArray(source?.['results'])
      ? (source['results'] as unknown[])
          .map((entry) => normalizeMediaDiagnosticResult(entry))
          .filter((entry): entry is MediaDiagnosticResult => !!entry)
      : [],
    settings: normalizeServerSettings(source?.['settings']),
  };
}

export function normalizeMediaRepairResponse(raw: unknown): MediaRepairResponse {
  const source = toRecord(raw);
  return {
    ok: Boolean(source?.['ok']),
    message: toOptionalString(source?.['message']) ?? '',
    repairs: Array.isArray(source?.['repairs'])
      ? (source['repairs'] as unknown[]).map((entry) => String(entry))
      : [],
  };
}

export function normalizeMediaCleanupResponse(raw: unknown): MediaCleanupResponse {
  const source = toRecord(raw);
  return {
    ok: Boolean(source?.['ok']),
    message: toOptionalString(source?.['message']) ?? '',
    cleanup: normalizeMediaCleanupResult(source?.['cleanup']),
  };
}

export function normalizeMediaCleanupResult(raw: unknown): MediaCleanupResult | null {
  const source = toRecord(raw);
  if (!source) {
    return null;
  }

  const storage = toRecord(source['storage']);
  return {
    ok: Boolean(source['ok'] ?? true),
    message: String(source['message'] ?? ''),
    dryRun: Boolean(source['dryRun'] ?? true),
    prefixes: Array.isArray(source['prefixes'])
      ? (source['prefixes'] as unknown[]).map((entry) => String(entry))
      : [],
    scannedFiles: Number(source['scannedFiles'] ?? 0),
    referencedFiles: Number(source['referencedFiles'] ?? 0),
    orphanedFiles: Number(source['orphanedFiles'] ?? 0),
    deletedFiles: Number(source['deletedFiles'] ?? 0),
    totalOrphanBytes: Number(source['totalOrphanBytes'] ?? 0),
    files: Array.isArray(source['files'])
      ? (source['files'] as unknown[])
          .map((entry) => normalizeMediaCleanupFile(entry))
          .filter((entry): entry is MediaCleanupFile => !!entry)
      : [],
    errors: Array.isArray(source['errors'])
      ? (source['errors'] as unknown[]).map((entry) => String(entry))
      : [],
    storageBackend: toOptionalString(storage?.['backend']),
    storageProvider: toOptionalString(storage?.['provider']),
  };
}

export function normalizeMediaCleanupFile(raw: unknown): MediaCleanupFile | null {
  const source = toRecord(raw);
  if (!source) {
    return null;
  }

  return {
    path: String(source['path'] ?? ''),
    sizeBytes: toOptionalNumber(source['sizeBytes']),
  };
}

export function normalizeServerSettings(raw: unknown): ServerSettings | null {
  const source = toRecord(raw);
  if (!source) {
    return null;
  }
  return {
    mediaRoot: String(source['mediaRoot'] ?? ''),
    mediaUrl: String(source['mediaUrl'] ?? ''),
    debug: Boolean(source['debug']),
  };
}

export function normalizeMediaDiagnosticResult(raw: unknown): MediaDiagnosticResult | null {
  const source = toRecord(raw);
  if (!source) {
    return null;
  }
  return {
    model: String(source['model'] ?? ''),
    id: Number(source['id'] ?? 0),
    field: String(source['field'] ?? ''),
    path: String(source['path'] ?? ''),
    absPath: String(source['absPath'] ?? ''),
    exists: Boolean(source['exists']),
    url: String(source['url'] ?? ''),
    fileLink: toOptionalString(source['fileLink']),
    discrepancy: Boolean(source['discrepancy']),
  };
}
