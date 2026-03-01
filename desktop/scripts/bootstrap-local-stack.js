"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

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

function resolveComposeCommand() {
  const composeV2 = spawnSync("docker", ["compose", "version"], { stdio: "ignore" });
  if (composeV2.status === 0) {
    return ["docker", "compose"];
  }

  const composeV1 = spawnSync("docker-compose", ["version"], { stdio: "ignore" });
  if (composeV1.status === 0) {
    return ["docker-compose"];
  }
  throw new Error("Docker Compose is not available.");
}

function run(cmd, args, opts = {}) {
  const result = spawnSync(cmd, args, {
    stdio: "inherit",
    env: opts.env || process.env,
    cwd: opts.cwd || process.cwd(),
  });
  if (result.status !== 0) {
    throw new Error(`Command failed: ${cmd} ${args.join(" ")}`);
  }
}

function sleep(ms) {
  spawnSync("sh", ["-lc", `sleep ${Math.max(0, Number(ms) / 1000)}`], {
    stdio: "ignore",
  });
}

function runWithRetry(cmd, args, opts = {}) {
  const attempts = Math.max(1, Number(opts.attempts) || 1);
  const delayMs = Math.max(0, Number(opts.delayMs) || 0);
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      run(cmd, args, opts);
      return;
    } catch (error) {
      lastError = error;
      if (attempt < attempts) {
        console.log(`[bootstrap] Retry ${attempt}/${attempts} failed. Waiting ${delayMs}ms...`);
        sleep(delayMs);
      }
    }
  }
  throw lastError;
}

function main() {
  const desktopRoot = path.resolve(__dirname, "..");
  const repoRoot = path.resolve(desktopRoot, "..");

  parseEnvFile(path.join(repoRoot, ".env"));
  parseEnvFile(path.join(desktopRoot, ".env"));

  const composeFile = path.resolve(
    process.env.DESKTOP_LOCAL_COMPOSE_FILE || path.join(repoRoot, "docker-compose-desktop-stack.yml"),
  );
  const basename = path.basename(composeFile);
  if (!basename.includes("desktop-stack")) {
    throw new Error(
      `Refusing bootstrap on non-desktop compose file: ${composeFile}. Use docker-compose-desktop-stack.yml only.`,
    );
  }

  const projectName = String(process.env.DESKTOP_LOCAL_COMPOSE_PROJECT || "revisbali-desktop-local").trim();
  const localDataPath = path.resolve(
    process.env.DESKTOP_LOCAL_DATA_PATH || path.join(os.homedir(), ".revisbali-desktop-runtime"),
  );
  const localDbPath = path.resolve(process.env.DESKTOP_LOCAL_DB_PATH || path.join(localDataPath, "postgresql"));

  for (const dirPath of [
    localDataPath,
    localDbPath,
    path.join(localDataPath, "media"),
    path.join(localDataPath, "db"),
    path.join(localDataPath, "logs"),
    path.join(localDataPath, "staticfiles"),
    path.join(localDataPath, "backups"),
  ]) {
    fs.mkdirSync(dirPath, { recursive: true });
  }

  const env = {
    ...process.env,
    DATA_PATH: localDataPath,
    DB_PATH: localDbPath,
    DESKTOP_DB_HOST: process.env.DESKTOP_DB_HOST || process.env.DESKTOP_LOCAL_DB_HOST || "db",
    DESKTOP_DB_PORT: process.env.DESKTOP_DB_PORT || process.env.DESKTOP_LOCAL_DB_PORT || "5432",
    DESKTOP_DB_NAME: process.env.DESKTOP_DB_NAME || process.env.DESKTOP_LOCAL_DB_NAME || "business_suite",
    DESKTOP_DB_USER: process.env.DESKTOP_DB_USER || process.env.DESKTOP_LOCAL_DB_USER || "postgres",
    DESKTOP_DB_PASS: process.env.DESKTOP_DB_PASS || process.env.DESKTOP_LOCAL_DB_PASS || "postgres",
    DB_HOST: process.env.DESKTOP_DB_HOST || process.env.DESKTOP_LOCAL_DB_HOST || "db",
    DB_PORT: process.env.DESKTOP_DB_PORT || process.env.DESKTOP_LOCAL_DB_PORT || "5432",
    DB_NAME: process.env.DESKTOP_DB_NAME || process.env.DESKTOP_LOCAL_DB_NAME || "business_suite",
    DB_USER: process.env.DESKTOP_DB_USER || process.env.DESKTOP_LOCAL_DB_USER || "postgres",
    DB_PASS: process.env.DESKTOP_DB_PASS || process.env.DESKTOP_LOCAL_DB_PASS || "postgres",
    DESKTOP_SECRET_KEY: process.env.DESKTOP_SECRET_KEY || process.env.SECRET_KEY || "desktop-local-secret-key-change-me",
    DESKTOP_APP_DOMAIN: process.env.DESKTOP_APP_DOMAIN || "127.0.0.1",
    DESKTOP_REDIS_HOST: process.env.DESKTOP_REDIS_HOST || process.env.DESKTOP_LOCAL_REDIS_HOST || "redis",
    DESKTOP_REDIS_PORT: process.env.DESKTOP_REDIS_PORT || process.env.DESKTOP_LOCAL_REDIS_PORT || "6379",
    REDIS_HOST: process.env.DESKTOP_REDIS_HOST || process.env.DESKTOP_LOCAL_REDIS_HOST || "redis",
    REDIS_PORT: process.env.DESKTOP_REDIS_PORT || process.env.DESKTOP_LOCAL_REDIS_PORT || "6379",
    LOCAL_SYNC_ENABLED: process.env.LOCAL_SYNC_ENABLED || "true",
    LOCAL_SYNC_NODE_ID: process.env.LOCAL_SYNC_NODE_ID || "desktop-local-node",
    LOCAL_MEDIA_ENCRYPTION_ENABLED: "true",
    LOCAL_MEDIA_ENCRYPTION_KEY: process.env.LOCAL_MEDIA_ENCRYPTION_KEY || "bootstrap-placeholder-key",
    SITE_ADMIN_USERNAME:
      process.env.DESKTOP_SITE_ADMIN_USERNAME || process.env.SITE_ADMIN_USERNAME || "revisadmin",
    SITE_ADMIN_EMAIL:
      process.env.DESKTOP_SITE_ADMIN_EMAIL || process.env.SITE_ADMIN_EMAIL || "info@example.com",
    SITE_ADMIN_PASSWORD:
      process.env.DESKTOP_SITE_ADMIN_PASSWORD || process.env.SITE_ADMIN_PASSWORD || "P12345678!",
    SYSTEM_USER_EMAIL: process.env.SYSTEM_USER_EMAIL || "desktop-local@revisbali.local",
    SYSTEM_USER_PASSWORD: process.env.SYSTEM_USER_PASSWORD || "desktop-local-change-me",
  };

  const [composeCmd, ...composeBaseArgs] = resolveComposeCommand();
  const composeArgs = ["-f", composeFile, "--project-name", projectName];

  console.log("\n[bootstrap] Starting desktop stack containers...");
  run(
    composeCmd,
    [...composeBaseArgs, ...composeArgs, "--profile", "app", "up", "-d", "db", "redis"],
    { env, cwd: repoRoot },
  );
  run(
    composeCmd,
    [
      ...composeBaseArgs,
      ...composeArgs,
      "--profile",
      "app",
      "up",
      "-d",
      "--build",
      "--force-recreate",
      "bs-core",
      "bs-worker",
      "bs-frontend",
    ],
    { env, cwd: repoRoot },
  );

  console.log("\n[bootstrap] Running migrations...");
  runWithRetry(
    composeCmd,
    [...composeBaseArgs, ...composeArgs, "exec", "-T", "bs-core", "python", "manage.py", "migrate", "--noinput"],
    { env, cwd: repoRoot, attempts: 20, delayMs: 3000 },
  );

  console.log("\n[bootstrap] Ensuring desktop admin login user...");
  runWithRetry(
    composeCmd,
    [...composeBaseArgs, ...composeArgs, "exec", "-T", "bs-core", "python", "manage.py", "createsuperuserifnotexists"],
    { env, cwd: repoRoot, attempts: 10, delayMs: 2000 },
  );
  runWithRetry(
    composeCmd,
    [
      ...composeBaseArgs,
      ...composeArgs,
      "exec",
      "-T",
      "bs-core",
      "python",
      "manage.py",
      "shell",
      "-c",
      [
        "import os",
        "from django.contrib.auth import get_user_model",
        "U = get_user_model()",
        "username = os.environ.get('SITE_ADMIN_USERNAME', 'revisadmin')",
        "email = os.environ.get('SITE_ADMIN_EMAIL', 'info@example.com')",
        "password = os.environ.get('SITE_ADMIN_PASSWORD', 'P12345678!')",
        "user, _ = U.objects.get_or_create(username=username)",
        "user.email = email",
        "user.is_superuser = True",
        "user.is_staff = True",
        "user.is_active = True",
        "user.set_password(password)",
        "user.save()",
        "print(f'Ensured admin user: {username}')",
      ].join("; "),
    ],
    { env, cwd: repoRoot, attempts: 10, delayMs: 2000 },
  );

  console.log("\n[bootstrap] Done.");
  console.log(`[bootstrap] Compose file: ${composeFile}`);
  console.log(`[bootstrap] Project name: ${projectName}`);
  console.log(`[bootstrap] Data path: ${localDataPath}`);
  console.log(`[bootstrap] Desktop app domain: ${env.DESKTOP_APP_DOMAIN}`);
  console.log(`[bootstrap] Admin username: ${env.SITE_ADMIN_USERNAME}`);
  console.log("[bootstrap] Admin password source: DESKTOP_SITE_ADMIN_PASSWORD/SITE_ADMIN_PASSWORD (or default)");
  console.log("[bootstrap] Next: start Electron and unlock Local Vault in /admin/server.");
}

main();
