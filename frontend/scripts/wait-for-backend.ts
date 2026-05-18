const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000';
const DEFAULT_READY_PATH = '/api/health/';
const DEFAULT_WAIT_TIMEOUT_MS = 90_000;
const DEFAULT_POLL_INTERVAL_MS = 1_000;
const DEFAULT_REQUEST_TIMEOUT_MS = 2_500;

function readPositiveInteger(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback;
  }

  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function formatElapsed(ms: number): string {
  if (ms < 1_000) {
    return `${ms}ms`;
  }

  return `${(ms / 1_000).toFixed(1)}s`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildReadyUrl(): string {
  const explicitReadyUrl = process.env['BACKEND_READY_URL']?.trim();
  if (explicitReadyUrl) {
    return explicitReadyUrl;
  }

  const backendUrl = stripTrailingSlash(process.env['BACKEND_URL']?.trim() || DEFAULT_BACKEND_URL);
  return new URL(DEFAULT_READY_PATH, `${backendUrl}/`).toString();
}

type ProbeResult = { ok: true; status: number } | { ok: false; status?: number; reason: string };

async function probeBackend(url: string, requestTimeoutMs: number): Promise<ProbeResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), requestTimeoutMs);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });

    if (response.ok) {
      return { ok: true, status: response.status };
    }

    return {
      ok: false,
      status: response.status,
      reason: `received HTTP ${response.status}`,
    };
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return { ok: false, reason };
  } finally {
    clearTimeout(timeout);
  }
}

async function main(): Promise<void> {
  const readyUrl = buildReadyUrl();
  const waitTimeoutMs = readPositiveInteger(
    process.env['BACKEND_READY_TIMEOUT_MS'],
    DEFAULT_WAIT_TIMEOUT_MS,
  );
  const pollIntervalMs = readPositiveInteger(
    process.env['BACKEND_READY_INTERVAL_MS'],
    DEFAULT_POLL_INTERVAL_MS,
  );
  const requestTimeoutMs = readPositiveInteger(
    process.env['BACKEND_READY_REQUEST_TIMEOUT_MS'],
    DEFAULT_REQUEST_TIMEOUT_MS,
  );

  const startedAt = Date.now();
  let attempt = 0;
  let lastFailureMessage = 'backend readiness was not confirmed';

  console.log(
    `[start_public] Waiting for backend at ${readyUrl} (timeout=${waitTimeoutMs}ms, interval=${pollIntervalMs}ms)...`,
  );

  while (Date.now() - startedAt < waitTimeoutMs) {
    attempt += 1;
    const result = await probeBackend(readyUrl, requestTimeoutMs);

    if (result.ok) {
      console.log(
        `[start_public] Backend ready after ${formatElapsed(Date.now() - startedAt)} (attempt ${attempt}, HTTP ${result.status}).`,
      );
      return;
    }

    lastFailureMessage = result.status
      ? `${result.reason} from ${readyUrl}`
      : `${result.reason} while reaching ${readyUrl}`;

    if (attempt === 1 || attempt % 5 === 0) {
      console.log(`[start_public] Still waiting: ${lastFailureMessage}`);
    }

    await sleep(pollIntervalMs);
  }

  console.error(
    `[start_public] Backend did not become ready within ${formatElapsed(waitTimeoutMs)}. Last probe: ${lastFailureMessage}.`,
  );
  process.exit(1);
}

void main();
