const express = require('express');
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');
const ngrok = require('@ngrok/ngrok');
const { createProxyMiddleware } = require('http-proxy-middleware');

const app = express();
const host = process.env.HOST || '127.0.0.1';
const port = Number(process.env.PORT || 4999);
const backendUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
const ngrokRequired = String(process.env.NGROK_REQUIRED || 'false').toLowerCase() === 'true';
const distPath = path.join(__dirname, 'dist', 'business-suite-frontend', 'browser');
const spaIndexPath = fs.existsSync(path.join(distPath, 'index.html'))
  ? path.join(distPath, 'index.html')
  : path.join(distPath, 'index.csr.html');

let server;
let listener;

function killExistingProcesses() {
  // Kill any process holding the target port
  try {
    const pids = execSync(`lsof -ti TCP:${port}`, { encoding: 'utf8' }).trim();
    if (pids) {
      pids.split('\n').forEach((pid) => {
        try {
          process.kill(Number(pid), 'SIGKILL');
          console.log(`Killed stale process on port ${port} (PID ${pid})`);
        } catch {
          // already gone
        }
      });
      // Give OS a moment to release the socket
      execSync('sleep 0.3');
    }
  } catch {
    // lsof exits non-zero when nothing is found — that's fine
  }

  // Disconnect any lingering ngrok sessions via SDK
  try {
    ngrok.disconnect();
  } catch {
    // best effort
  }
}

const backendProxy = createProxyMiddleware({
  target: backendUrl,
  changeOrigin: true,
  xfwd: true,
  // pathFilter preserves the full path — app.use('/api', proxy) would strip
  // the /api prefix before forwarding which breaks Django URL routing
  pathFilter: (pathname) =>
    pathname.startsWith('/api/') ||
    pathname === '/api' ||
    pathname.startsWith('/_observability') ||
    pathname.startsWith('/media/'),
});

app.use(backendProxy);

app.use(express.static(distPath, { index: false }));

// SPA fallback
app.get(/.*/, (_req, res) => {
  res.sendFile(spaIndexPath);
});

function buildNgrokOptions() {
  const token = process.env.NGROK_AUTHTOKEN;

  // Use explicit 127.0.0.1 to avoid macOS AirPlay (ControlCenter) on *:5000
  // request_header_add injects the skip header so the ngrok interstitial is
  // bypassed automatically for all browser visitors on the free plan
  const options = {
    addr: `127.0.0.1:${port}`,
    request_header_add: ['ngrok-skip-browser-warning: 1'],
  };

  if (token) {
    options.authtoken = token;
  }

  if (process.env.NGROK_DOMAIN) options.domain = process.env.NGROK_DOMAIN;
  if (process.env.NGROK_REGION) options.region = process.env.NGROK_REGION;

  return options;
}

async function start() {
  killExistingProcesses();

  server = app.listen(port, host, async () => {
    console.log(`Static server running on http://${host}:${port}`);
    console.log(`Serving: ${distPath}`);
    console.log(`Proxying API/media to: ${backendUrl}`);

    try {
      listener = await ngrok.forward(buildNgrokOptions());
      console.log(`HTTPS tunnel ready: ${listener.url()}`);
    } catch (error) {
      console.error('Failed to start ngrok tunnel:', error);
      if (ngrokRequired) {
        process.exitCode = 1;
        await shutdown();
        return;
      }

      console.warn('Continuing without ngrok tunnel. Local HTTP server remains available.');
      console.warn('Set NGROK_REQUIRED=true to fail fast when tunnel startup is mandatory.');
    }
  });
}

async function shutdown() {
  try {
    if (listener) {
      await listener.close();
      listener = undefined;
    }
    await ngrok.disconnect();
  } catch {
    // best effort
  }

  if (server) {
    await new Promise((resolve) => server.close(resolve));
  }
}

process.on('SIGINT', async () => {
  await shutdown();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await shutdown();
  process.exit(0);
});

start().catch(async (error) => {
  console.error('Startup error:', error);
  await shutdown();
  process.exit(1);
});
