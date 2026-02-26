'use strict';

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const REQUIRED_SERVICES = ['db', 'redis', 'bs-core', 'bs-worker', 'bs-frontend'];
const DEFAULT_STATUS = {
  available: false,
  running: false,
  healthy: false,
  reason: null,
  lastError: null,
};

class DesktopRuntimeManager {
  constructor({
    projectRoot,
    composeFile,
    projectName = 'revisbali-desktop-local',
    localFrontendUrl = 'http://127.0.0.1:14200',
    localBackendHealthUrl = 'http://127.0.0.1:18000/api/app-config/',
    localSyncStateUrl = 'http://127.0.0.1:18000/api/sync/state/',
    localDataPath,
    localDbPath,
    remoteSyncBaseUrl = '',
    remoteSyncToken = '',
    remoteSyncNodeId = '',
    getMediaEncryptionKey,
    log,
  } = {}) {
    this.projectRoot = projectRoot || path.resolve(__dirname, '..', '..');
    this.composeFile = composeFile || path.join(this.projectRoot, 'docker-compose-desktop-stack.yml');
    this.projectName = String(projectName || 'revisbali-desktop-local').trim() || 'revisbali-desktop-local';
    this.localFrontendUrl = String(localFrontendUrl || 'http://127.0.0.1:14200').trim();
    this.localBackendHealthUrl = String(localBackendHealthUrl || 'http://127.0.0.1:18000/api/app-config/').trim();
    this.localSyncStateUrl = String(localSyncStateUrl || 'http://127.0.0.1:18000/api/sync/state/').trim();
    this.localDataPath =
      localDataPath || path.join(this.projectRoot, '.desktop-local-runtime');
    this.localDbPath = localDbPath || path.join(this.localDataPath, 'postgresql');
    this.remoteSyncBaseUrl = String(remoteSyncBaseUrl || '').trim().replace(/\/+$/, '');
    this.remoteSyncToken = String(remoteSyncToken || '').trim();
    this.remoteSyncNodeId = String(remoteSyncNodeId || '').trim();
    this.getMediaEncryptionKey =
      typeof getMediaEncryptionKey === 'function' ? getMediaEncryptionKey : () => null;
    this.log = typeof log === 'function' ? log : () => {};

    this.composeCommand = this.resolveComposeCommand();
    this.status = {
      ...DEFAULT_STATUS,
      available: Boolean(this.composeCommand && fs.existsSync(this.composeFile)),
      localFrontendUrl: this.localFrontendUrl,
      localBackendHealthUrl: this.localBackendHealthUrl,
      localSyncStateUrl: this.localSyncStateUrl,
      composeFile: this.composeFile,
    };
  }

  resolveComposeCommand() {
    try {
      const composeV2 = spawnSync('docker', ['compose', 'version'], {
        stdio: 'ignore',
      });
      if (composeV2.status === 0) {
        return ['docker', 'compose'];
      }
    } catch {
      // Fall through to docker-compose probe.
    }

    try {
      const composeV1 = spawnSync('docker-compose', ['version'], {
        stdio: 'ignore',
      });
      if (composeV1.status === 0) {
        return ['docker-compose'];
      }
    } catch {
      // No compose command available.
    }

    return null;
  }

  buildComposeEnv() {
    const key = String(this.getMediaEncryptionKey() || '').trim();
    return {
      ...process.env,
      DATA_PATH: this.localDataPath,
      DB_PATH: this.localDbPath,
      DESKTOP_DB_HOST: process.env.DESKTOP_DB_HOST || process.env.DESKTOP_LOCAL_DB_HOST || 'db',
      DESKTOP_DB_PORT: process.env.DESKTOP_DB_PORT || process.env.DESKTOP_LOCAL_DB_PORT || '5432',
      DESKTOP_DB_NAME: process.env.DESKTOP_DB_NAME || process.env.DESKTOP_LOCAL_DB_NAME || 'business_suite',
      DESKTOP_DB_USER: process.env.DESKTOP_DB_USER || process.env.DESKTOP_LOCAL_DB_USER || 'postgres',
      DESKTOP_DB_PASS: process.env.DESKTOP_DB_PASS || process.env.DESKTOP_LOCAL_DB_PASS || 'postgres',
      DB_HOST: process.env.DESKTOP_DB_HOST || process.env.DESKTOP_LOCAL_DB_HOST || 'db',
      DB_PORT: process.env.DESKTOP_DB_PORT || process.env.DESKTOP_LOCAL_DB_PORT || '5432',
      DB_NAME: process.env.DESKTOP_DB_NAME || process.env.DESKTOP_LOCAL_DB_NAME || 'business_suite',
      DB_USER: process.env.DESKTOP_DB_USER || process.env.DESKTOP_LOCAL_DB_USER || 'postgres',
      DB_PASS: process.env.DESKTOP_DB_PASS || process.env.DESKTOP_LOCAL_DB_PASS || 'postgres',
      DESKTOP_SECRET_KEY: process.env.DESKTOP_SECRET_KEY || process.env.SECRET_KEY || 'desktop-local-secret-key-change-me',
      DESKTOP_APP_DOMAIN: process.env.DESKTOP_APP_DOMAIN || '127.0.0.1',
      DESKTOP_REDIS_HOST: process.env.DESKTOP_REDIS_HOST || process.env.DESKTOP_LOCAL_REDIS_HOST || 'redis',
      DESKTOP_REDIS_PORT: process.env.DESKTOP_REDIS_PORT || process.env.DESKTOP_LOCAL_REDIS_PORT || '6379',
      DESKTOP_HUEY_REDIS_DB: process.env.DESKTOP_HUEY_REDIS_DB || process.env.DESKTOP_LOCAL_HUEY_REDIS_DB || '0',
      REDIS_HOST: process.env.DESKTOP_REDIS_HOST || process.env.DESKTOP_LOCAL_REDIS_HOST || 'redis',
      REDIS_PORT: process.env.DESKTOP_REDIS_PORT || process.env.DESKTOP_LOCAL_REDIS_PORT || '6379',
      HUEY_REDIS_DB: process.env.DESKTOP_HUEY_REDIS_DB || process.env.DESKTOP_LOCAL_HUEY_REDIS_DB || '0',
      LOCAL_SYNC_ENABLED: process.env.LOCAL_SYNC_ENABLED || 'true',
      LOCAL_SYNC_NODE_ID:
        this.remoteSyncNodeId || process.env.LOCAL_SYNC_NODE_ID || 'desktop-local-node',
      LOCAL_SYNC_REMOTE_BASE_URL:
        this.remoteSyncBaseUrl || process.env.LOCAL_SYNC_REMOTE_BASE_URL || '',
      LOCAL_SYNC_REMOTE_TOKEN:
        this.remoteSyncToken || process.env.LOCAL_SYNC_REMOTE_TOKEN || '',
      LOCAL_MEDIA_ENCRYPTION_ENABLED: 'true',
      LOCAL_MEDIA_ENCRYPTION_KEY: key,
    };
  }

  ensureRuntimeDirectories() {
    const requiredDirs = [
      this.localDataPath,
      this.localDbPath,
      path.join(this.localDataPath, 'media'),
      path.join(this.localDataPath, 'db'),
      path.join(this.localDataPath, 'logs'),
      path.join(this.localDataPath, 'staticfiles'),
      path.join(this.localDataPath, 'backups'),
    ];
    for (const dirPath of requiredDirs) {
      fs.mkdirSync(dirPath, { recursive: true });
    }
  }

  execCompose(args, { timeoutMs = 300_000 } = {}) {
    if (!this.composeCommand || !fs.existsSync(this.composeFile)) {
      throw new Error('Docker Compose not available or compose file missing');
    }

    this.ensureRuntimeDirectories();

    const [cmd, ...baseArgs] = this.composeCommand;
    const result = spawnSync(
      cmd,
      [
        ...baseArgs,
        '-f',
        this.composeFile,
        '--project-name',
        this.projectName,
        ...args,
      ],
      {
        cwd: this.projectRoot,
        env: this.buildComposeEnv(),
        encoding: 'utf8',
        timeout: timeoutMs,
      },
    );

    if (result.error) {
      throw result.error;
    }
    if (result.status !== 0) {
      throw new Error(result.stderr || result.stdout || `compose exit ${result.status}`);
    }
    return result.stdout || '';
  }

  parseRunningServices(rawOutput) {
    const output = String(rawOutput || '').trim();
    if (!output) {
      return new Set();
    }
    const names = output
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
    return new Set(names);
  }

  async fetchJson(url, { timeoutMs = 3000, headers = {} } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: { Accept: 'application/json', ...headers },
        signal: controller.signal,
      });
      if (!response.ok) {
        return { ok: false, status: response.status, body: null };
      }
      const body = await response.json().catch(() => null);
      return { ok: true, status: response.status, body };
    } finally {
      clearTimeout(timer);
    }
  }

  async checkHealth() {
    try {
      const backendProbe = await this.fetchJson(this.localBackendHealthUrl, {
        timeoutMs: 4000,
      });
      if (!backendProbe.ok) {
        return false;
      }
    } catch {
      return false;
    }

    try {
      const response = await fetch(this.localFrontendUrl, {
        method: 'GET',
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async refreshStatus() {
    if (!this.status.available) {
      this.status.running = false;
      this.status.healthy = false;
      this.status.reason = 'docker_compose_unavailable';
      return this.getStatus();
    }

    try {
      const raw = this.execCompose(['ps', '--services', '--status', 'running'], {
        timeoutMs: 20_000,
      });
      const runningServices = this.parseRunningServices(raw);
      const running = REQUIRED_SERVICES.every((serviceName) => runningServices.has(serviceName));
      const healthy = running ? await this.checkHealth() : false;
      this.status.running = running;
      this.status.healthy = healthy;
      this.status.reason = running ? (healthy ? null : 'healthcheck_failed') : 'services_not_running';
      this.status.lastError = null;
      return this.getStatus();
    } catch (error) {
      this.status.running = false;
      this.status.healthy = false;
      this.status.reason = 'status_probe_failed';
      this.status.lastError = String(error);
      return this.getStatus();
    }
  }

  async waitForHealthy({ timeoutMs = 180_000, pollIntervalMs = 3000 } = {}) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
      const status = await this.refreshStatus();
      if (status.running && status.healthy) {
        return status;
      }
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    }
    return this.getStatus();
  }

  async start() {
    if (!this.status.available) {
      return this.getStatus();
    }

    const key = String(this.getMediaEncryptionKey() || '').trim();
    if (!key) {
      this.status.running = false;
      this.status.healthy = false;
      this.status.reason = 'vault_locked';
      this.status.lastError = 'Vault is locked: missing local media encryption key';
      return this.getStatus();
    }

    try {
      this.execCompose(
        ['--profile', 'app', 'up', '-d', ...REQUIRED_SERVICES],
        { timeoutMs: 600_000 },
      );
    } catch (error) {
      this.status.running = false;
      this.status.healthy = false;
      this.status.reason = 'start_failed';
      this.status.lastError = String(error);
      return this.getStatus();
    }

    return this.waitForHealthy();
  }

  async stop() {
    if (!this.status.available) {
      return this.getStatus();
    }
    try {
      this.execCompose(['stop', ...REQUIRED_SERVICES], { timeoutMs: 180_000 });
      this.status.running = false;
      this.status.healthy = false;
      this.status.reason = null;
      this.status.lastError = null;
    } catch (error) {
      this.status.reason = 'stop_failed';
      this.status.lastError = String(error);
    }
    return this.getStatus();
  }

  async resetLocalData() {
    try {
      await this.stop();
    } catch {
      // Best effort; continue with wipe.
    }

    try {
      fs.rmSync(this.localDataPath, { recursive: true, force: true });
      this.ensureRuntimeDirectories();
      this.status.reason = 'local_data_reset';
      this.status.lastError = null;
    } catch (error) {
      this.status.reason = 'local_data_reset_failed';
      this.status.lastError = String(error);
    }
    return this.getStatus();
  }

  async getSyncStatus() {
    const status = await this.refreshStatus();
    if (!status.running || !status.healthy) {
      return {
        running: false,
        lastPushAt: null,
        lastPullAt: null,
        lastError: status.lastError || status.reason || null,
      };
    }

    try {
      const syncHeaders = {};
      if (this.remoteSyncToken) {
        syncHeaders.Authorization = `Bearer ${this.remoteSyncToken}`;
      }
      const response = await this.fetchJson(this.localSyncStateUrl, {
        timeoutMs: 4000,
        headers: syncHeaders,
      });
      const remoteCursor = response?.body?.remoteCursor || {};
      return {
        running: true,
        lastPushAt: remoteCursor.lastPushedAt || null,
        lastPullAt: remoteCursor.lastPulledAt || null,
        lastError: remoteCursor.lastError || null,
      };
    } catch (error) {
      return {
        running: true,
        lastPushAt: null,
        lastPullAt: null,
        lastError: String(error),
      };
    }
  }

  getStatus() {
    return {
      ...this.status,
      available: Boolean(this.status.available),
      running: Boolean(this.status.running),
      healthy: Boolean(this.status.healthy),
    };
  }
}

module.exports = {
  DesktopRuntimeManager,
};
