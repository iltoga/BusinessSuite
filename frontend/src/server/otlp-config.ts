type OtlpConfigSource =
  | 'explicit-traces-endpoint'
  | 'explicit-base-endpoint'
  | 'grafana-cloud-endpoint'
  | 'disabled';

export type ResolvedOtlpTracesConfig = {
  endpoint: string;
  enabled: boolean;
  source: OtlpConfigSource;
  headers: Record<string, string>;
  headerNames: string[];
  timeoutMs: number;
};

const DEFAULT_OTLP_TIMEOUT_MS = 10_000;

const parseKvCsv = (rawValue: string | undefined): Record<string, string> => {
  const parsed: Record<string, string> = {};
  for (const item of (rawValue || '').split(',')) {
    const pair = item.trim();
    if (!pair || !pair.includes('=')) {
      continue;
    }

    const separatorIndex = pair.indexOf('=');
    const key = pair.slice(0, separatorIndex).trim();
    const value = pair.slice(separatorIndex + 1).trim();
    if (key) {
      parsed[key] = value;
    }
  }
  return parsed;
};

const parsePositiveInt = (rawValue: string | undefined): number | null => {
  if (!rawValue) {
    return null;
  }

  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }

  return Math.floor(parsed);
};

const normalizeBaseEndpoint = (rawValue: string | undefined): string =>
  String(rawValue || '')
    .trim()
    .replace(/\/+$/, '');

const resolveEndpoint = (
  env: NodeJS.ProcessEnv,
): { endpoint: string; source: OtlpConfigSource } => {
  const tracesEndpoint = normalizeBaseEndpoint(env['OTEL_EXPORTER_OTLP_TRACES_ENDPOINT']);
  if (tracesEndpoint) {
    return { endpoint: tracesEndpoint, source: 'explicit-traces-endpoint' };
  }

  const baseEndpoint = normalizeBaseEndpoint(env['OTEL_EXPORTER_OTLP_ENDPOINT']);
  if (baseEndpoint) {
    return { endpoint: `${baseEndpoint}/v1/traces`, source: 'explicit-base-endpoint' };
  }

  const grafanaBaseEndpoint = normalizeBaseEndpoint(env['GRAFANA_CLOUD_OTLP_ENDPOINT']);
  if (grafanaBaseEndpoint) {
    return { endpoint: `${grafanaBaseEndpoint}/v1/traces`, source: 'grafana-cloud-endpoint' };
  }

  return { endpoint: '', source: 'disabled' };
};

const buildGrafanaCloudAuthorization = (env: NodeJS.ProcessEnv): string | null => {
  const username = String(env['GRAFANA_CLOUD_OTLP_USER'] || '').trim();
  const password = String(env['GRAFANA_CLOUD_OTLP_API_KEY'] || '').trim();
  if (!username || !password) {
    return null;
  }

  return `Basic ${Buffer.from(`${username}:${password}`).toString('base64')}`;
};

export const resolveOtlpTracesConfig = (env: NodeJS.ProcessEnv): ResolvedOtlpTracesConfig => {
  const endpointResolution = resolveEndpoint(env);
  const headers = {
    ...parseKvCsv(env['OTEL_EXPORTER_OTLP_HEADERS']),
    ...parseKvCsv(env['OTEL_EXPORTER_OTLP_TRACES_HEADERS']),
  };

  if (!headers['Authorization']) {
    const grafanaAuthorization = buildGrafanaCloudAuthorization(env);
    if (grafanaAuthorization) {
      headers['Authorization'] = grafanaAuthorization;
    }
  }

  const timeoutMs =
    parsePositiveInt(env['OTEL_EXPORTER_OTLP_TRACES_TIMEOUT']) ??
    parsePositiveInt(env['OTEL_EXPORTER_OTLP_TIMEOUT']) ??
    parsePositiveInt(env['OTEL_EXPORTER_OTLP_TIMEOUT_MS']) ??
    DEFAULT_OTLP_TIMEOUT_MS;

  const tracesExporter = String(env['OTEL_TRACES_EXPORTER'] || 'otlp')
    .trim()
    .toLowerCase();
  const enabled = Boolean(endpointResolution.endpoint) && tracesExporter !== 'none';

  return {
    endpoint: endpointResolution.endpoint,
    enabled,
    source: endpointResolution.source,
    headers,
    headerNames: Object.keys(headers).sort(),
    timeoutMs,
  };
};
