import {
  AngularNodeAppEngine,
  createNodeRequestHandler,
  isMainModule,
  writeResponseToNodeResponse,
} from '@angular/ssr/node';

// Increase Node EventEmitter default listener limit to avoid "MaxListenersExceededWarning"
// when tooling attaches multiple listeners (dev servers, test harnesses, hot-reload, etc.).
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const events = require('events') as typeof import('events');
  if (events && typeof events.EventEmitter === 'function') {
    events.EventEmitter.defaultMaxListeners = Math.max(
      events.EventEmitter.defaultMaxListeners || 0,
      20,
    );
  }
  // Also increase process-level limit if available
  (process as any).setMaxListeners?.(20);
  console.debug('[Server] increased EventEmitter.defaultMaxListeners to 20');
} catch (e) {
  // Best-effort; don't fail startup
}

import express from 'express';
import { randomBytes } from 'node:crypto';
import { promises as fs } from 'node:fs';
import { request as httpRequest, type OutgoingHttpHeaders, type RequestOptions } from 'node:http';
import { request as httpsRequest } from 'node:https';
import { dirname, join } from 'node:path';
import { generateNonce } from './csp';

const browserDistFolder = join(import.meta.dirname, '../browser');

const app = express();
const angularApp = new AngularNodeAppEngine();
const traceContextSymbol = Symbol('traceContext');
const clientLogPath = '/_observability/client-logs';
const clientLogWindowMs = Number(process.env['CLIENT_LOG_RATE_LIMIT_WINDOW_MS'] || '60000');
const clientLogMaxPerWindow = Number(process.env['CLIENT_LOG_RATE_LIMIT_MAX'] || '60');

type ClientLogBucket = {
  windowStartMs: number;
  count: number;
};

const clientLogBuckets = new Map<string, ClientLogBucket>();

const frontendLogPath =
  process.env['FE_LOG_FILE_PATH'] ||
  (process.env['NODE_ENV'] === 'production'
    ? '/logs/frontend.log'
    : join(process.cwd(), '..', 'backend', 'logs', 'frontend.log'));
const serverLogDedupWindowMs = Number(process.env['SERVER_LOG_DEDUP_WINDOW_MS'] || '4000');
const serverLogDedupCache = new Map<string, number>();
const noisyServerLogPatterns = [
  '[Server] increased EventEmitter.defaultMaxListeners to 20',
  '[Server] setMaxListeners(20) applied to Node server',
  '[SSR Server] Proxying API to:',
  '[SSR] Handling request:',
  '[LoggerService] Console overrides initialized. Client logs will be forwarded to server.',
  'Angular is running in development mode.',
  'Angular hydrated ',
];

type OtlpPrimitive = string | number | boolean;

type RequestTraceContext = {
  traceId: string;
  spanId: string;
  traceFlags: string;
  parentSpanId?: string;
  spanName: string;
  requestPath: string;
  requestQuery: string;
  requestHost: string;
  startTimeUnixNano: string;
};

type TracedRequest = express.Request & {
  [traceContextSymbol]?: RequestTraceContext;
};

type ParsedTraceparent = {
  traceId: string;
  spanId: string;
  traceFlags: string;
};

const OTLP_TRACES_ENDPOINT =
  process.env['OTEL_EXPORTER_OTLP_TRACES_ENDPOINT'] ||
  (process.env['OTEL_EXPORTER_OTLP_ENDPOINT']
    ? `${String(process.env['OTEL_EXPORTER_OTLP_ENDPOINT']).replace(/\/+$/, '')}/v1/traces`
    : '');
const OTLP_TRACES_ENABLED =
  Boolean(OTLP_TRACES_ENDPOINT) &&
  String(process.env['OTEL_TRACES_EXPORTER'] || 'otlp').toLowerCase() !== 'none';
const OTLP_SERVICE_NAME = process.env['OTEL_SERVICE_NAME'] || 'frontend';
const OTLP_SCOPE_NAME =
  process.env['OTEL_INSTRUMENTATION_SCOPE_NAME'] || 'revisbali.manual.frontend';
const OTLP_EXPORT_TIMEOUT_MS = Number(process.env['OTEL_EXPORTER_OTLP_TIMEOUT_MS'] || '1000');
const OTLP_RESOURCE_ATTRIBUTES = parseKvCsv(process.env['OTEL_RESOURCE_ATTRIBUTES'] || '');
OTLP_RESOURCE_ATTRIBUTES['service.name'] =
  OTLP_RESOURCE_ATTRIBUTES['service.name'] || OTLP_SERVICE_NAME;
let lastOtlpErrorLogAtMs = 0;

function parseKvCsv(rawValue: string): Record<string, string> {
  const parsed: Record<string, string> = {};
  for (const part of rawValue.split(',')) {
    const pair = part.trim();
    if (!pair) continue;
    const separatorIndex = pair.indexOf('=');
    if (separatorIndex <= 0) continue;
    const key = pair.slice(0, separatorIndex).trim();
    const value = pair.slice(separatorIndex + 1).trim();
    if (key) parsed[key] = value;
  }
  return parsed;
}

function nowUnixNano(): string {
  return (BigInt(Date.now()) * 1_000_000n).toString();
}

function randomHex(byteLength: number): string {
  return randomBytes(byteLength).toString('hex');
}

function parseTraceparent(value: string | string[] | undefined): ParsedTraceparent | undefined {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw) return undefined;
  const trimmed = raw.trim().toLowerCase();
  const match = /^([\da-f]{2})-([\da-f]{32})-([\da-f]{16})-([\da-f]{2})$/.exec(trimmed);
  if (!match) return undefined;
  return {
    traceId: match[2],
    spanId: match[3],
    traceFlags: match[4],
  };
}

function buildTraceparent(ctx: RequestTraceContext): string {
  return `00-${ctx.traceId}-${ctx.spanId}-${ctx.traceFlags}`;
}

function shouldTraceRequest(req: express.Request): boolean {
  const path = req.path || '/';
  if (path === clientLogPath) return false;
  if (path.startsWith('/assets/')) return false;
  if (path.startsWith('/favicon')) return false;
  if (/\.(?:js|mjs|css|map|png|jpe?g|gif|svg|ico|webp|woff2?)$/i.test(path)) return false;
  return true;
}

function toOtlpAttribute(key: string, value: OtlpPrimitive): Record<string, unknown> {
  if (typeof value === 'boolean') {
    return { key, value: { boolValue: value } };
  }
  if (typeof value === 'number' && Number.isInteger(value)) {
    return { key, value: { intValue: String(value) } };
  }
  if (typeof value === 'number') {
    return { key, value: { doubleValue: value } };
  }
  return { key, value: { stringValue: value } };
}

function logOtlpExportWarning(message: string): void {
  const now = Date.now();
  if (now - lastOtlpErrorLogAtMs < 10_000) {
    return;
  }
  lastOtlpErrorLogAtMs = now;
  console.warn(message);
}

async function exportSpan(
  ctx: RequestTraceContext,
  attributes: Record<string, OtlpPrimitive>,
  statusCode: number,
): Promise<void> {
  if (!OTLP_TRACES_ENABLED || !OTLP_TRACES_ENDPOINT) {
    return;
  }

  const span: Record<string, unknown> = {
    traceId: ctx.traceId,
    spanId: ctx.spanId,
    name: ctx.spanName.slice(0, 300),
    kind: 2, // SPAN_KIND_SERVER
    startTimeUnixNano: ctx.startTimeUnixNano,
    endTimeUnixNano: nowUnixNano(),
    attributes: Object.entries(attributes).map(([key, value]) => toOtlpAttribute(key, value)),
    status: { code: statusCode >= 500 ? 2 : 1 },
  };

  if (ctx.parentSpanId) {
    span['parentSpanId'] = ctx.parentSpanId;
  }

  const payload = {
    resourceSpans: [
      {
        resource: {
          attributes: Object.entries(OTLP_RESOURCE_ATTRIBUTES).map(([key, value]) =>
            toOtlpAttribute(key, value),
          ),
        },
        scopeSpans: [
          {
            scope: { name: OTLP_SCOPE_NAME },
            spans: [span],
          },
        ],
      },
    ],
  };

  const abortController = new AbortController();
  const timeout = setTimeout(() => abortController.abort(), OTLP_EXPORT_TIMEOUT_MS);
  try {
    const response = await fetch(OTLP_TRACES_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: abortController.signal,
    });
    if (!response.ok) {
      const body = (await response.text()).slice(0, 600);
      logOtlpExportWarning(`[OTLP] export failed (${response.status}): ${body}`);
    }
  } catch (error) {
    logOtlpExportWarning(`[OTLP] export error: ${String(error)}`);
  } finally {
    clearTimeout(timeout);
  }
}

const normalizeLogForDedup = (value: string) =>
  value
    .replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z/g, '<ts>')
    .replace(/\b\d{10,13}\b/g, '<epoch>');

const shouldDropServerLog = (level: string, serialized: string) => {
  if (noisyServerLogPatterns.some((pattern) => serialized.includes(pattern))) {
    return true;
  }

  const now = Date.now();
  const dedupKey = `${level}|${normalizeLogForDedup(serialized)}`.slice(0, 1500);
  const lastSeen = serverLogDedupCache.get(dedupKey);
  serverLogDedupCache.set(dedupKey, now);

  if (serverLogDedupCache.size > 1500) {
    for (const [cacheKey, seenAt] of serverLogDedupCache.entries()) {
      if (now - seenAt > serverLogDedupWindowMs * 5) {
        serverLogDedupCache.delete(cacheKey);
      }
    }
  }

  return typeof lastSeen === 'number' && now - lastSeen < serverLogDedupWindowMs;
};

if (OTLP_TRACES_ENABLED) {
  console.info(`[OTLP] frontend tracing enabled, exporting to ${OTLP_TRACES_ENDPOINT}`);
}

const appendServerLog = (level: string, args: unknown[]) => {
  const timestamp = new Date().toISOString();
  const serialized = args
    .map((arg) => {
      if (typeof arg === 'string') return arg;
      try {
        return JSON.stringify(arg);
      } catch {
        return String(arg);
      }
    })
    .join(' ');
  if (shouldDropServerLog(level, serialized)) {
    return;
  }
  const line = `[SSR] [${level.toUpperCase()}] [${timestamp}] ${serialized}\n`;
  fs.mkdir(dirname(frontendLogPath), { recursive: true })
    .then(() => fs.appendFile(frontendLogPath, line))
    .catch(() => {
      // Best effort only; do not break request handling on log write failures.
    });
};

const originalConsole = {
  log: console.log.bind(console),
  info: console.info.bind(console),
  warn: console.warn.bind(console),
  error: console.error.bind(console),
  debug: console.debug.bind(console),
};

console.log = (...args: unknown[]) => {
  originalConsole.log(...args);
  appendServerLog('log', args);
};
console.info = (...args: unknown[]) => {
  originalConsole.info(...args);
  appendServerLog('info', args);
};
console.warn = (...args: unknown[]) => {
  originalConsole.warn(...args);
  appendServerLog('warn', args);
};
console.error = (...args: unknown[]) => {
  originalConsole.error(...args);
  appendServerLog('error', args);
};
console.debug = (...args: unknown[]) => {
  originalConsole.debug(...args);
  appendServerLog('debug', args);
};

const getClientRateKey = (req: express.Request) => {
  const xff = req.headers['x-forwarded-for'];
  const forwardedIp = Array.isArray(xff)
    ? xff[0]
    : typeof xff === 'string'
      ? xff.split(',')[0]
      : '';
  const ip = forwardedIp?.trim() || req.ip || 'unknown';
  const userAgent = String(req.headers['user-agent'] || '').slice(0, 120);
  return `${ip}|${userAgent}`;
};

const isClientLogRateLimited = (key: string, nowMs: number) => {
  if (clientLogBuckets.size > 2000) {
    for (const [bucketKey, bucket] of clientLogBuckets.entries()) {
      if (nowMs - bucket.windowStartMs > clientLogWindowMs * 2) {
        clientLogBuckets.delete(bucketKey);
      }
    }
  }

  const existing = clientLogBuckets.get(key);
  if (!existing || nowMs - existing.windowStartMs >= clientLogWindowMs) {
    clientLogBuckets.set(key, { windowStartMs: nowMs, count: 1 });
    return false;
  }

  existing.count += 1;
  if (existing.count > clientLogMaxPerWindow) {
    // Avoid flooding SSR logs while still indicating drops happened.
    if (existing.count === clientLogMaxPerWindow + 1) {
      console.warn(
        `[BROWSER] [WARN] [${new Date(nowMs).toISOString()}] client log rate limit reached key=${key} window_ms=${clientLogWindowMs} max=${clientLogMaxPerWindow}`,
      );
    }
    return true;
  }

  return false;
};

/**
 * Handle browser-side logs - Must be defined BEFORE proxy to avoid being forwarded to Django backend
 */
app.post(clientLogPath, express.json({ limit: '16kb' }), (req, res) => {
  const nowMs = Date.now();
  const rateKey = getClientRateKey(req);
  if (isClientLogRateLimited(rateKey, nowMs)) {
    // Return 204 to keep browser console/network noise low.
    res.sendStatus(204);
    return;
  }

  const { level, message, details, url, username } = req.body || {};
  const timestamp = new Date().toISOString();
  const normalizedLevel =
    level === 'error' || level === 'warn' || level === 'debug' || level === 'info' ? level : 'info';
  const truncatedMessage = String(message || '').slice(0, 4000);
  const normalizedUsername =
    typeof username === 'string' && username.trim() ? username.trim().slice(0, 120) : '';
  const userPrefix = normalizedUsername ? `[user:${normalizedUsername}] ` : '';
  // Prefix helps Grafana/Alloy filters
  const logMessage = `[BROWSER] [${normalizedLevel.toUpperCase()}] [${timestamp}] ${userPrefix}${url ? '(' + url + ') ' : ''}${truncatedMessage}${details ? ' ' + JSON.stringify(details) : ''}`;

  switch (normalizedLevel) {
    case 'error':
      console.error(logMessage);
      break;
    case 'warn':
      console.warn(logMessage);
      break;
    case 'debug':
      console.debug(logMessage);
      break;
    default:
      console.info(logMessage);
  }

  res.sendStatus(204);
});

app.use((req, res, next) => {
  if (!OTLP_TRACES_ENABLED || !shouldTraceRequest(req)) {
    next();
    return;
  }

  const parsedParent = parseTraceparent(req.headers['traceparent']);
  const traceContext: RequestTraceContext = {
    traceId: parsedParent?.traceId || randomHex(16),
    spanId: randomHex(8),
    traceFlags: parsedParent?.traceFlags || '01',
    parentSpanId: parsedParent?.spanId,
    spanName: `${req.method} ${req.path || '/'}`,
    requestPath: req.path || '/',
    requestQuery: req.url.includes('?') ? req.url.split('?').slice(1).join('?') : '',
    requestHost: req.get('host') || '',
    startTimeUnixNano: nowUnixNano(),
  };
  (req as TracedRequest)[traceContextSymbol] = traceContext;

  let exported = false;
  const finishSpan = (statusCode: number) => {
    if (exported) return;
    exported = true;

    const attributes: Record<string, OtlpPrimitive> = {
      'http.request.method': req.method,
      'http.response.status_code': statusCode,
      'url.path': traceContext.requestPath,
      'url.query': traceContext.requestQuery,
      'server.address': traceContext.requestHost,
      'http.route': req.route?.path ? String(req.route.path) : traceContext.requestPath,
    };

    void exportSpan(traceContext, attributes, statusCode);
  };

  res.on('finish', () => finishSpan(res.statusCode || 200));
  res.on('close', () => {
    if (!res.writableEnded) {
      finishSpan(res.statusCode || 499);
    }
  });

  next();
});

/**
 * Proxy API requests to the backend
 */
const backendUrl = process.env['BACKEND_URL'] || 'http://127.0.0.1:8000';
const proxiedPathPrefixes = ['/api', '/media', '/uploads', '/staticfiles'] as const;
console.log(`[SSR Server] Proxying API to: ${backendUrl}`);

const shouldProxyPath = (urlPath: string): boolean =>
  proxiedPathPrefixes.some((prefix) => urlPath === prefix || urlPath.startsWith(`${prefix}/`));

app.use((req, res, next) => {
  const requestPath = req.originalUrl || req.url || '/';
  if (!shouldProxyPath(requestPath)) {
    next();
    return;
  }

  const target = new URL(requestPath, backendUrl);
  const isHttps = target.protocol === 'https:';
  const requestImpl = isHttps ? httpsRequest : httpRequest;
  const headers: OutgoingHttpHeaders = {
    ...req.headers,
    host: target.host,
  };

  const traceContext = (req as TracedRequest)[traceContextSymbol];
  if (traceContext) {
    headers['traceparent'] = buildTraceparent(traceContext);
    if (!headers['tracestate'] && req.headers['tracestate']) {
      headers['tracestate'] = Array.isArray(req.headers['tracestate'])
        ? req.headers['tracestate'].join(',')
        : req.headers['tracestate'];
    }
  }

  if (!headers['x-forwarded-host'] && req.headers.host) {
    headers['x-forwarded-host'] = req.headers.host;
  }
  if (!headers['x-forwarded-proto']) {
    headers['x-forwarded-proto'] = req.protocol;
  }

  const options: RequestOptions = {
    protocol: target.protocol,
    hostname: target.hostname,
    port: target.port || (isHttps ? 443 : 80),
    method: req.method,
    path: `${target.pathname}${target.search}`,
    headers,
  };
  const backendRequest = requestImpl(
    isHttps ? { ...options, rejectUnauthorized: false } : options,
    (backendResponse) => {
      res.status(backendResponse.statusCode ?? 502);

      for (const [headerName, headerValue] of Object.entries(backendResponse.headers)) {
        if (headerValue !== undefined) {
          res.setHeader(headerName, headerValue);
        }
      }

      backendResponse.pipe(res);
    },
  );

  backendRequest.on('error', (error) => {
    console.error(`[SSR Server] API proxy error for ${requestPath}:`, error);
    if (!res.headersSent) {
      res.status(502).json({ detail: 'Failed to reach backend API.' });
    } else {
      res.end();
    }
  });

  req.on('aborted', () => {
    backendRequest.destroy();
  });

  req.pipe(backendRequest);
});

/**
 * Serve static files from /browser
 */
app.use(
  express.static(browserDistFolder, {
    maxAge: '1y',
    index: false,
    redirect: false,
  }),
);

/**
 * Handle all other requests by rendering the Angular application.
 * Adds optional CSP nonce generation and injection when `CSP_ENABLED=true`.
 */
app.use(async (req, res, next) => {
  console.log(`[SSR] Handling request: ${req.url}`);
  try {
    const response = await angularApp.handle(req);
    if (response?.status === 302) {
      console.log(`[SSR] Redirecting ${req.url} to ${response.headers.get('location')}`);
    }
    if (!response) return next();

    // Access env vars with bracket notation to satisfy TS index signature typing
    const cspEnabled = (process.env['CSP_ENABLED'] || '').toLowerCase() === 'true';
    const cspMode = process.env['CSP_MODE'] || 'report-only'; // report-only|enforce

    // Read content-type from Headers if available
    let contentType = '';
    if (response.headers && typeof (response.headers as any).get === 'function') {
      contentType =
        (response.headers as any).get('content-type') ??
        (response.headers as any).get('Content-Type') ??
        '';
    } else if (response.headers && typeof response.headers === 'object') {
      // Fallback for plain object headers
      contentType =
        (response.headers as any)['content-type'] ??
        (response.headers as any)['Content-Type'] ??
        '';
    }

    // Inject server-provided brand variables into HTML so the client can pick them up
    if (typeof response.body === 'string' && contentType.includes('text/html')) {
      // Logos are now loaded statically from assets/config.json; runtime injection removed.
      let runtimeTitle = process.env['APP_TITLE'] || 'BusinessSuite';
      try {
        const cfgPath = join(browserDistFolder, 'assets', 'config.json');
        const rawCfg = await fs.readFile(cfgPath, 'utf8');
        const parsedCfg = JSON.parse(rawCfg);
        if (parsedCfg && parsedCfg.title) runtimeTitle = String(parsedCfg.title);
      } catch (e) {
        /* ignore: missing or unreadable config.json */
      }

      // Simple HTML-escape for title insertion
      const escapeHtml = (s: string) =>
        s
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');

      const escapedTitle = escapeHtml(runtimeTitle);

      // Log resolved runtime brand to make debugging in production easier
      console.debug('[SSR] Resolved branding:', { title: runtimeTitle });

      // Prepare HTML with replaced title (done once)
      const responseHtml = String(response.body).replace(
        /<title>.*?<\/title>/i,
        `<title>${escapedTitle}</title>`,
      );

      if (cspEnabled) {
        const nonce = generateNonce();

        // Prepare a modified Headers instance based on existing headers
        let modifiedHeaders: Headers;
        if (response.headers && typeof (response.headers as any).forEach === 'function') {
          modifiedHeaders = new Headers();
          // copy existing headers
          (response.headers as any).forEach((value: string, key: string) =>
            modifiedHeaders.set(key, value),
          );
        } else if (response.headers && typeof response.headers === 'object') {
          modifiedHeaders = new Headers(Object.entries(response.headers as any));
        } else {
          modifiedHeaders = new Headers();
        }

        modifiedHeaders.set('x-csp-nonce', nonce);
        modifiedHeaders.set('x-csp-mode', cspMode);

        // Also set headers on the Node response (ensures nginx sees them when proxied)
        res.setHeader('X-CSP-Nonce', nonce);
        res.setHeader('X-CSP-Mode', cspMode);

        // Inject Angular root attribute so Angular uses the nonce without requiring index.html rewrites
        let modifiedBody = responseHtml.replace(/<app(\s|>)/, `<app ngCspNonce="${nonce}"$1`);

        // Inject server config from .env into the page so the app picks it up immediately
        const mockAuthEnv = (process.env['MOCK_AUTH_ENABLED'] || 'False').trim();
        const appTitleEnv = process.env['APP_TITLE'] || 'BusinessSuite';
        const fcmSenderIdEnv = (process.env['FCM_SENDER_ID'] || '').trim();
        const fcmProjectNumberEnv = (process.env['FCM_PROJECT_NUMBER'] || '').trim();
        const fcmVapidPublicKeyEnv = (process.env['FCM_VAPID_PUBLIC_KEY'] || '').trim();
        const fcmProjectIdEnv = (process.env['FCM_PROJECT_ID'] || '').trim();
        const fcmWebApiKeyEnv = (process.env['FCM_WEB_API_KEY'] || '').trim();
        const fcmWebAppIdEnv = (process.env['FCM_WEB_APP_ID'] || '').trim();
        const fcmWebAuthDomainEnv = (process.env['FCM_WEB_AUTH_DOMAIN'] || '').trim();
        const fcmWebStorageBucketEnv = (process.env['FCM_WEB_STORAGE_BUCKET'] || '').trim();
        const fcmWebMeasurementIdEnv = (process.env['FCM_WEB_MEASUREMENT_ID'] || '').trim();
        const configScript = `<script nonce="${nonce}">(function(){
          window.APP_CONFIG={
            MOCK_AUTH_ENABLED: ${JSON.stringify(mockAuthEnv)},
            title: ${JSON.stringify(appTitleEnv)},
            fcmSenderId: ${JSON.stringify(fcmSenderIdEnv)},
            fcmProjectNumber: ${JSON.stringify(fcmProjectNumberEnv)},
            fcmVapidPublicKey: ${JSON.stringify(fcmVapidPublicKeyEnv)},
            fcmProjectId: ${JSON.stringify(fcmProjectIdEnv)},
            fcmWebApiKey: ${JSON.stringify(fcmWebApiKeyEnv)},
            fcmWebAppId: ${JSON.stringify(fcmWebAppIdEnv)},
            fcmWebAuthDomain: ${JSON.stringify(fcmWebAuthDomainEnv)},
            fcmWebStorageBucket: ${JSON.stringify(fcmWebStorageBucketEnv)},
            fcmWebMeasurementId: ${JSON.stringify(fcmWebMeasurementIdEnv)}
          };
        })();</script>`;
        modifiedBody = modifiedBody.replace(/<head(\s|>)/i, `<head$1\n${configScript}`);

        // Inject a small script with the server's title only (logo files are not injected)
        // Also add a quick class so CSS can show the correct logo immediately and avoid a flash
        const brandScript = `<script nonce="${nonce}">(function(){
          window.APP_BRAND = { title: ${JSON.stringify(runtimeTitle)} };
          try{document.documentElement.classList.add('app-brand-ready')}catch(e){}
          try{document.title=${JSON.stringify(runtimeTitle)};}catch(e){}
        })();</script>`;
        modifiedBody = modifiedBody.replace(/<head(\s|>)/i, `<head$1\n${brandScript}`);

        // Build a modified response object (avoid mutating readonly properties)
        const modifiedResponse = {
          ...response,
          headers: modifiedHeaders,
          body: modifiedBody,
        } as any;

        writeResponseToNodeResponse(modifiedResponse, res);
        return;
      } else {
        // Non-CSP path: inject script without nonce
        // Non-CSP path: inject script and add a quick class so CSS shows the correct logo ASAP
        const brandScript = `<script>(function(){
          window.APP_BRAND = { title: ${JSON.stringify(runtimeTitle)} };
          try{document.documentElement.classList.add('app-brand-ready')}catch(e){}
          try{document.title=${JSON.stringify(runtimeTitle)};}catch(e){}
        })();</script>`;
        let modifiedBody = responseHtml.replace(/<head(\s|>)/i, `<head$1\n${brandScript}`);

        // Inject server config from .env into the page
        const mockAuthEnv = (process.env['MOCK_AUTH_ENABLED'] || 'False').trim();
        const appTitleEnv = process.env['APP_TITLE'] || 'BusinessSuite';
        const fcmSenderIdEnv = (process.env['FCM_SENDER_ID'] || '').trim();
        const fcmProjectNumberEnv = (process.env['FCM_PROJECT_NUMBER'] || '').trim();
        const fcmVapidPublicKeyEnv = (process.env['FCM_VAPID_PUBLIC_KEY'] || '').trim();
        const fcmProjectIdEnv = (process.env['FCM_PROJECT_ID'] || '').trim();
        const fcmWebApiKeyEnv = (process.env['FCM_WEB_API_KEY'] || '').trim();
        const fcmWebAppIdEnv = (process.env['FCM_WEB_APP_ID'] || '').trim();
        const fcmWebAuthDomainEnv = (process.env['FCM_WEB_AUTH_DOMAIN'] || '').trim();
        const fcmWebStorageBucketEnv = (process.env['FCM_WEB_STORAGE_BUCKET'] || '').trim();
        const fcmWebMeasurementIdEnv = (process.env['FCM_WEB_MEASUREMENT_ID'] || '').trim();
        const configScript = `<script>(function(){
          window.APP_CONFIG={
            MOCK_AUTH_ENABLED: ${JSON.stringify(mockAuthEnv)},
            title: ${JSON.stringify(appTitleEnv)},
            fcmSenderId: ${JSON.stringify(fcmSenderIdEnv)},
            fcmProjectNumber: ${JSON.stringify(fcmProjectNumberEnv)},
            fcmVapidPublicKey: ${JSON.stringify(fcmVapidPublicKeyEnv)},
            fcmProjectId: ${JSON.stringify(fcmProjectIdEnv)},
            fcmWebApiKey: ${JSON.stringify(fcmWebApiKeyEnv)},
            fcmWebAppId: ${JSON.stringify(fcmWebAppIdEnv)},
            fcmWebAuthDomain: ${JSON.stringify(fcmWebAuthDomainEnv)},
            fcmWebStorageBucket: ${JSON.stringify(fcmWebStorageBucketEnv)},
            fcmWebMeasurementId: ${JSON.stringify(fcmWebMeasurementIdEnv)}
          };
        })();</script>`;
        modifiedBody = modifiedBody.replace(/<head(\s|>)/i, `<head$1\n${configScript}`);

        const modifiedResponse = {
          ...response,
          body: modifiedBody,
        } as any;

        writeResponseToNodeResponse(modifiedResponse, res);
        return;
      }
    }

    // Default: forward original response
    writeResponseToNodeResponse(response, res);
  } catch (err) {
    next(err);
  }
});

/**
 * Start the server if this module is the main entry point, or it is ran via PM2.
 * The server listens on the port defined by the `PORT` environment variable, or defaults to 4000.
 */
const isBuildExecution = (process.env['NG_BUILD'] || '').toLowerCase() === 'true';

if (!isBuildExecution && (isMainModule(import.meta.url) || process.env['pm_id'])) {
  const port = Number(process.env['PORT'] || 4000);
  const host = process.env['HOST'] || '0.0.0.0';
  // Capture the server instance so we can tune its EventEmitter listener limit.
  const server = app.listen(port, host, (error) => {
    if (error) {
      throw error;
    }

    console.log(`Node Express server listening on http://${host}:${port}`);
  });

  // Increase the max listeners to avoid "MaxListenersExceededWarning" when dev servers
  // or tooling attach multiple listeners (e.g., hot-reload, PM2, test harnesses).
  try {
    // 0 = unlimited; prefer a reasonable cap like 20 to avoid hiding real leaks
    (server as any).setMaxListeners?.(20);
    console.debug('[Server] setMaxListeners(20) applied to Node server');
  } catch (e) {
    // No-op: best-effort fix
  }
}

/**
 * Request handler used by the Angular CLI (for dev-server and during build) or Firebase Cloud Functions.
 */
export const reqHandler = createNodeRequestHandler(app);
