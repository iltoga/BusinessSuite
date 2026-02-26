"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const COLORS = {
  reset: "\x1b[0m",
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  cyan: "\x1b[36m",
};

const EXPECTED_SERVICES = ["db", "redis", "bs-core", "bs-worker", "bs-frontend"];
const DEFAULT_COMMAND_TIMEOUT_MS = 20000;

function colorize(color, text) {
  if (!process.stdout.isTTY) {
    return text;
  }
  return `${COLORS[color] || ""}${text}${COLORS.reset}`;
}

function statusTag(status) {
  if (status === "OK") {
    return colorize("green", "[OK]");
  }
  if (status === "FAIL") {
    return colorize("red", "[FAIL]");
  }
  return colorize("yellow", "[WARN]");
}

function printCheck(status, name, detail = "") {
  console.log(`${statusTag(status)} ${name}${detail ? ` - ${detail}` : ""}`);
}

function parseEnvFile(envPath) {
  if (!fs.existsSync(envPath)) {
    return;
  }
  const raw = fs.readFileSync(envPath, "utf8");
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const idx = trimmed.indexOf("=");
    if (idx <= 0) {
      continue;
    }
    const key = trimmed.slice(0, idx).trim();
    if (!key || process.env[key] !== undefined) {
      continue;
    }
    let value = trimmed.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}

function runCommand(cmd, args, opts = {}) {
  const result = spawnSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    cwd: opts.cwd || process.cwd(),
    env: opts.env || process.env,
    timeout: Number(opts.timeoutMs || DEFAULT_COMMAND_TIMEOUT_MS),
    maxBuffer: Number(opts.maxBuffer || 8 * 1024 * 1024),
  });
  return {
    ok: result.status === 0 && !result.error,
    status: result.status,
    stdout: String(result.stdout || ""),
    stderr: String(result.stderr || ""),
    error: result.error || null,
  };
}

function commandError(result, fallback) {
  if (result.error) {
    return String(result.error);
  }
  const stderr = String(result.stderr || "").trim();
  if (stderr) {
    return stderr;
  }
  return fallback;
}

function parseComposePsJson(rawOutput) {
  const raw = String(rawOutput || "").trim();
  if (!raw) {
    return [];
  }
  if (raw.startsWith("[")) {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  }
  const rows = [];
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    rows.push(JSON.parse(trimmed));
  }
  return rows;
}

function isTruthy(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(normalized);
}

async function fetchWithTimeout(url, timeoutMs = 4000, headers = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json", ...headers },
      signal: controller.signal,
    });
    return { ok: true, status: response.status };
  } catch (error) {
    return { ok: false, error: String(error) };
  } finally {
    clearTimeout(timer);
  }
}

async function probeHttpWithRetry(
  url,
  {
    attempts = 1,
    delayMs = 0,
    timeoutMs = 4000,
    headers = {},
    acceptedStatuses = [],
    onRetry = null,
  } = {},
) {
  let last = { ok: false, status: null, error: "not_started" };
  for (let i = 0; i < attempts; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    const current = await fetchWithTimeout(url, timeoutMs, headers);
    last = current;
    if (current.ok && acceptedStatuses.includes(current.status)) {
      return { success: true, status: current.status, last: current };
    }
    if (i + 1 < attempts && delayMs > 0) {
      if (typeof onRetry === "function") {
        onRetry({ nextAttempt: i + 2, attempts, current });
      }
      // eslint-disable-next-line no-await-in-loop
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  return { success: false, status: last.status || null, last };
}

function createRecorder() {
  const checks = [];
  function add(status, name, detail) {
    checks.push({ status, name, detail });
    printCheck(status, name, detail);
  }
  return {
    checks,
    ok: (name, detail) => add("OK", name, detail),
    warn: (name, detail) => add("WARN", name, detail),
    fail: (name, detail) => add("FAIL", name, detail),
  };
}

async function main() {
  console.log(colorize("cyan", "Desktop Local Doctor"));
  console.log(colorize("cyan", "===================="));

  const desktopRoot = path.resolve(__dirname, "..");
  const repoRoot = path.resolve(desktopRoot, "..");

  parseEnvFile(path.join(repoRoot, ".env"));
  parseEnvFile(path.join(desktopRoot, ".env"));

  const composeFile = path.resolve(
    process.env.DESKTOP_LOCAL_COMPOSE_FILE || path.join(repoRoot, "docker-compose-desktop-stack.yml"),
  );
  const projectName = String(process.env.DESKTOP_LOCAL_COMPOSE_PROJECT || "revisbali-desktop-local").trim();
  const localFrontendUrl = String(process.env.DESKTOP_LOCAL_FRONTEND_URL || "http://127.0.0.1:14200").trim();
  const localBackendHealthUrl = String(
    process.env.DESKTOP_LOCAL_BACKEND_HEALTH_URL || "http://127.0.0.1:18000/api/app-config/",
  ).trim();
  const localSyncStateUrl = String(
    process.env.DESKTOP_LOCAL_SYNC_STATE_URL || "http://127.0.0.1:18000/api/sync/state/",
  ).trim();
  const desktopAdminUsername = String(
    process.env.DESKTOP_SITE_ADMIN_USERNAME || process.env.SITE_ADMIN_USERNAME || "revisadmin",
  ).trim();

  const { checks, ok, warn, fail } = createRecorder();

  if (fs.existsSync(path.join(desktopRoot, ".env"))) {
    ok("desktop/.env present", path.join(desktopRoot, ".env"));
  } else {
    warn("desktop/.env present", "missing; defaults are used");
  }

  if (fs.existsSync(composeFile)) {
    ok("Desktop compose file", composeFile);
    if (!path.basename(composeFile).includes("desktop-stack")) {
      warn("Desktop compose filename", "compose file does not look desktop-specific");
    }
  } else {
    fail("Desktop compose file", `missing: ${composeFile}`);
  }

  if (isTruthy(process.env.DESKTOP_LOCAL_FIRST_ENABLED || "1")) {
    ok("Local-first toggle", "DESKTOP_LOCAL_FIRST_ENABLED is enabled");
  } else {
    warn("Local-first toggle", "DESKTOP_LOCAL_FIRST_ENABLED is disabled");
  }

  if (String(process.env.DESKTOP_REMOTE_SYNC_BASE_URL || "").trim()) {
    ok("Remote sync base URL", process.env.DESKTOP_REMOTE_SYNC_BASE_URL);
  } else {
    warn("Remote sync base URL", "DESKTOP_REMOTE_SYNC_BASE_URL is empty");
  }

  if (String(process.env.DESKTOP_REMOTE_SYNC_TOKEN || process.env.LOCAL_SYNC_REMOTE_TOKEN || "").trim()) {
    ok("Remote sync token", "configured");
  } else {
    warn("Remote sync token", "DESKTOP_REMOTE_SYNC_TOKEN/LOCAL_SYNC_REMOTE_TOKEN is empty");
  }

  const dockerVersion = runCommand("docker", ["version"], { timeoutMs: 15000 });
  if (dockerVersion.ok) {
    ok("Docker CLI", "available");
  } else {
    fail("Docker CLI", commandError(dockerVersion, "docker command failed"));
  }

  const composeVersion = runCommand("docker", ["compose", "version"], { timeoutMs: 15000 });
  if (composeVersion.ok) {
    ok("Docker Compose", composeVersion.stdout.trim() || "available");
  } else {
    fail("Docker Compose", commandError(composeVersion, "docker compose unavailable"));
  }

  const dockerInfo = runCommand("docker", ["info"], { timeoutMs: 20000 });
  const daemonReachable = dockerInfo.ok;
  if (daemonReachable) {
    ok("Docker daemon", "reachable");
  } else {
    fail("Docker daemon", commandError(dockerInfo, "not reachable"));
  }

  if (daemonReachable && fs.existsSync(composeFile)) {
    const runningServicesCmd = runCommand(
      "docker",
      ["compose", "-f", composeFile, "--project-name", projectName, "ps", "--services", "--status", "running"],
      { cwd: repoRoot, timeoutMs: 20000 },
    );
    if (!runningServicesCmd.ok) {
      fail("Desktop stack running", commandError(runningServicesCmd, "unable to query compose ps"));
    } else {
      const running = new Set(
        runningServicesCmd.stdout
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean),
      );
      for (const service of EXPECTED_SERVICES) {
        if (running.has(service)) {
          ok(`Service ${service}`, "running");
        } else {
          fail(`Service ${service}`, "not running");
        }
      }
    }

    const psJson = runCommand(
      "docker",
      ["compose", "-f", composeFile, "--project-name", projectName, "ps", "--format", "json"],
      { cwd: repoRoot, timeoutMs: 20000 },
    );
    if (psJson.ok) {
      try {
        const rows = parseComposePsJson(psJson.stdout);
        const byService = new Map(rows.map((row) => [row.Service, row]));
        for (const service of ["db", "redis"]) {
          const row = byService.get(service);
          if (!row) {
            continue;
          }
          const health = String(row.Health || "").trim().toLowerCase();
          if (!health) {
            warn(`Health ${service}`, "no explicit health reported");
          } else if (health === "healthy") {
            ok(`Health ${service}`, health);
          } else {
            fail(`Health ${service}`, health);
          }
        }
      } catch {
        warn("Compose JSON status", "unable to parse docker compose ps --format json output");
      }
    } else {
      warn("Compose JSON status", "docker compose ps --format json unavailable");
    }

    const coreDbHost = runCommand(
      "docker",
      ["compose", "-f", composeFile, "--project-name", projectName, "exec", "-T", "bs-core", "printenv", "DB_HOST"],
      { cwd: repoRoot, timeoutMs: 20000 },
    );
    if (coreDbHost.ok) {
      const value = String(coreDbHost.stdout || "").trim();
      if (value === "db") {
        ok("Desktop DB routing (bs-core)", "DB_HOST=db");
      } else {
        fail("Desktop DB routing (bs-core)", `DB_HOST=${value || "<empty>"} (expected db)`);
      }
    } else {
      warn("Desktop DB routing (bs-core)", "unable to read DB_HOST from bs-core");
    }

    const workerDbHost = runCommand(
      "docker",
      ["compose", "-f", composeFile, "--project-name", projectName, "exec", "-T", "bs-worker", "printenv", "DB_HOST"],
      { cwd: repoRoot, timeoutMs: 20000 },
    );
    if (workerDbHost.ok) {
      const value = String(workerDbHost.stdout || "").trim();
      if (value === "db") {
        ok("Desktop DB routing (bs-worker)", "DB_HOST=db");
      } else {
        fail("Desktop DB routing (bs-worker)", `DB_HOST=${value || "<empty>"} (expected db)`);
      }
    } else {
      warn("Desktop DB routing (bs-worker)", "unable to read DB_HOST from bs-worker");
    }

    const escapedUsername = desktopAdminUsername.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    const adminCheckScript = [
      "from django.contrib.auth import get_user_model",
      "U=get_user_model()",
      `print('yes' if U.objects.filter(username='${escapedUsername}', is_superuser=True, is_active=True).exists() else 'no')`,
    ].join(";");
    const adminUserCheck = runCommand(
      "docker",
      [
        "compose",
        "-f",
        composeFile,
        "--project-name",
        projectName,
        "exec",
        "-T",
        "bs-core",
        "python",
        "manage.py",
        "shell",
        "-c",
        adminCheckScript,
      ],
      { cwd: repoRoot, timeoutMs: 25000 },
    );
    if (adminUserCheck.ok) {
      const answer = String(adminUserCheck.stdout || "").trim().toLowerCase();
      if (answer.includes("yes")) {
        ok("Desktop admin login user", `${desktopAdminUsername} exists (superuser active)`);
      } else {
        fail("Desktop admin login user", `${desktopAdminUsername} missing or not superuser/active`);
      }
    } else {
      warn("Desktop admin login user", "unable to verify from bs-core");
    }
  }

  console.log(colorize("cyan", `[probe] Checking frontend: ${localFrontendUrl}`));
  const frontendProbe = await probeHttpWithRetry(localFrontendUrl, {
    attempts: 6,
    delayMs: 1500,
    timeoutMs: 3500,
    acceptedStatuses: [200, 301, 302, 307, 308],
    onRetry: ({ nextAttempt, attempts, current }) => {
      const reason = current.status ? `HTTP ${current.status}` : current.error || "unavailable";
      console.log(colorize("yellow", `[probe] Frontend retry ${nextAttempt}/${attempts} (${reason})`));
    },
  });
  if (frontendProbe.success) {
    ok("Local frontend URL", `${localFrontendUrl} -> HTTP ${frontendProbe.status}`);
  } else {
    fail("Local frontend URL", `${localFrontendUrl} unreachable`);
  }

  console.log(colorize("cyan", `[probe] Checking backend health: ${localBackendHealthUrl}`));
  const backendProbe = await probeHttpWithRetry(localBackendHealthUrl, {
    attempts: 8,
    delayMs: 2000,
    timeoutMs: 4000,
    acceptedStatuses: [200],
    onRetry: ({ nextAttempt, attempts, current }) => {
      const reason = current.status ? `HTTP ${current.status}` : current.error || "unavailable";
      console.log(colorize("yellow", `[probe] Backend retry ${nextAttempt}/${attempts} (${reason})`));
    },
  });
  if (backendProbe.success) {
    ok("Local backend health URL", `${localBackendHealthUrl} -> HTTP ${backendProbe.status}`);
  } else {
    if (backendProbe.status === 400) {
      fail(
        "Local backend health URL",
        `${localBackendHealthUrl} -> HTTP 400 (likely APP_DOMAIN/ALLOWED_HOSTS mismatch for local host)`,
      );
    } else {
      fail("Local backend health URL", `${localBackendHealthUrl} unavailable`);
    }
  }

  console.log(colorize("cyan", `[probe] Checking sync state: ${localSyncStateUrl}`));
  const syncProbe = await probeHttpWithRetry(localSyncStateUrl, {
    attempts: 8,
    delayMs: 2000,
    timeoutMs: 4000,
    acceptedStatuses: [200, 401, 403],
    onRetry: ({ nextAttempt, attempts, current }) => {
      const reason = current.status ? `HTTP ${current.status}` : current.error || "unavailable";
      console.log(colorize("yellow", `[probe] Sync retry ${nextAttempt}/${attempts} (${reason})`));
    },
  });
  if (syncProbe.success) {
    ok("Local sync state URL", `${localSyncStateUrl} -> HTTP ${syncProbe.status}`);
  } else {
    if (syncProbe.status === 400) {
      fail(
        "Local sync state URL",
        `${localSyncStateUrl} -> HTTP 400 (likely APP_DOMAIN/ALLOWED_HOSTS mismatch for local host)`,
      );
    } else {
      fail("Local sync state URL", `${localSyncStateUrl} unavailable`);
    }
  }

  const failed = checks.filter((item) => item.status === "FAIL").length;
  const warned = checks.filter((item) => item.status === "WARN").length;
  const passed = checks.filter((item) => item.status === "OK").length;

  console.log(
    colorize(
      failed > 0 ? "red" : warned > 0 ? "yellow" : "green",
      `\nSummary: ${passed} OK, ${warned} WARN, ${failed} FAIL`,
    ),
  );

  if (failed > 0) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(colorize("red", `[FAIL] doctor crashed: ${String(error)}`));
  process.exitCode = 1;
});
