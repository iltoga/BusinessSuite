import {
  AngularNodeAppEngine,
  createNodeRequestHandler,
  isMainModule,
  writeResponseToNodeResponse,
} from '@angular/ssr/node';
import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { join } from 'node:path';
import { generateNonce } from './csp';

const browserDistFolder = join(import.meta.dirname, '../browser');

const app = express();
const angularApp = new AngularNodeAppEngine();

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
    pathFilter: ['/api', '/media', '/staticfiles'],
  }),
);

/**
 * Serve modified assets at runtime for environment-driven overrides
 *
 * This endpoint lets us override values in /assets/config.json using
 * environment variables at container start time so the deployed image
 * doesn't need to be rebuilt when changing branding.
 */
import { promises as fs } from 'node:fs';

app.get('/assets/config.json', async (req, res, next) => {
  try {
    const cfgPath = join(browserDistFolder, 'assets', 'config.json');
    const raw = await fs.readFile(cfgPath, 'utf8');
    const cfg = JSON.parse(raw);

    // Allow container env vars to override the static config.json values
    const logoFilename = process.env['LOGO_FILENAME'];
    const logoInverted = process.env['LOGO_INVERTED_FILENAME'];

    const merged = {
      ...cfg,
      ...(logoFilename ? { logoFilename } : {}),
      ...(logoInverted ? { logoInvertedFilename: logoInverted } : {}),
    };

    // Log what we're returning to help ops debugging
    console.debug('[Server] /assets/config.json ->', merged);

    // Cache for a short amount of time in case env changes (unlikely) but still safe
    res.setHeader('Cache-Control', 'public, max-age=60');
    res.json(merged);
  } catch (err) {
    next(err);
  }
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
  try {
    const response = await angularApp.handle(req);
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
      const logoFilename = process.env['LOGO_FILENAME'] || 'logo_transparent.png';
      const logoInverted = process.env['LOGO_INVERTED_FILENAME'] || 'logo_inverted_transparent.png';

      // Log resolved runtime brand to make debugging in production easier
      console.debug('[SSR] Resolved branding:', { logoFilename, logoInverted });

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
        let modifiedBody = String(response.body).replace(
          /<app(\s|>)/,
          `<app ngCspNonce="${nonce}"$1`,
        );

        // Inject a small script with the server's logo choices (script must use nonce when CSP is enabled)
        // Also add a quick class so CSS can show the correct logo immediately and avoid a flash
        const logoScript = `<script nonce="${nonce}">(function(){
          window.APP_BRAND={logo:'/assets/${logoFilename}',logoInverted:'/assets/${logoInverted}'};
          try{document.documentElement.classList.add('app-brand-ready')}catch(e){}
        })();</script>`;
        modifiedBody = modifiedBody.replace(/<head(\s|>)/i, `<head$1\n${logoScript}`);

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
        const logoScript = `<script>(function(){
          window.APP_BRAND={logo:'/assets/${logoFilename}',logoInverted:'/assets/${logoInverted}'};
          try{document.documentElement.classList.add('app-brand-ready')}catch(e){}
        })();</script>`;
        const modifiedBody = String(response.body).replace(
          /<head(\s|>)/i,
          `<head$1\n${logoScript}`,
        );

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
  app.listen(port, host, (error) => {
    if (error) {
      throw error;
    }

    console.log(`Node Express server listening on http://${host}:${port}`);
  });
}

/**
 * Request handler used by the Angular CLI (for dev-server and during build) or Firebase Cloud Functions.
 */
export const reqHandler = createNodeRequestHandler(app);
