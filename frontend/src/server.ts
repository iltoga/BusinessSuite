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
import { createProxyMiddleware } from 'http-proxy-middleware';
import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import { generateNonce } from './csp';

const browserDistFolder = join(import.meta.dirname, '../browser');

const app = express();
const angularApp = new AngularNodeAppEngine();

/**
 * Handle browser-side logs - Must be defined BEFORE proxy to avoid being forwarded to Django backend
 */
app.post('/api/client-logs', express.json(), (req, res) => {
  const { level, message, details, url } = req.body;
  const timestamp = new Date().toISOString();
  // Prefix helps Grafana/Alloy filters
  const logMessage = `[BROWSER] [${level?.toUpperCase() || 'INFO'}] [${timestamp}] ${url ? '(' + url + ') ' : ''}${message}${details ? ' ' + JSON.stringify(details) : ''}`;

  switch (level) {
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

/**
 * Proxy API requests to the backend
 */
const backendUrl = process.env['BACKEND_URL'] || 'http://127.0.0.1:8000';
console.log(`[SSR Server] Proxying API to: ${backendUrl}`);

app.use(
  createProxyMiddleware({
    target: backendUrl,
    changeOrigin: true,
    secure: false,
    logger: console,
    pathFilter: ['/api', '/media', '/uploads', '/staticfiles'],
  }),
);

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
        const configScript = `<script nonce="${nonce}">(function(){
          window.APP_CONFIG={
            MOCK_AUTH_ENABLED: ${JSON.stringify(mockAuthEnv)},
            title: ${JSON.stringify(appTitleEnv)}
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
        const configScript = `<script>(function(){
          window.APP_CONFIG={
            MOCK_AUTH_ENABLED: ${JSON.stringify(mockAuthEnv)},
            title: ${JSON.stringify(appTitleEnv)}
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
if (isMainModule(import.meta.url) || process.env['pm_id']) {
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
