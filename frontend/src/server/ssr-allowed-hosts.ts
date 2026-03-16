const LOCAL_ALLOWED_HOSTS = ['localhost', '127.0.0.1', '::1'] as const;

const splitHostCandidates = (value: string): string[] =>
  value
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);

const normalizeHost = (value: string): string | null => {
  const candidate = value.trim();
  if (!candidate) {
    return null;
  }

  const wildcardCandidate = candidate.startsWith('*.') ? candidate.slice(2) : candidate;
  if (wildcardCandidate.includes('://')) {
    try {
      const parsed = new URL(wildcardCandidate);
      if (!parsed.hostname) {
        return null;
      }
      return candidate.startsWith('*.')
        ? `*.${parsed.hostname.toLowerCase()}`
        : parsed.hostname.toLowerCase();
    } catch {
      return null;
    }
  }

  if (candidate.startsWith('*.')) {
    const domain = candidate.slice(2).toLowerCase().replace(/\/$/, '');
    return domain ? `*.${domain}` : null;
  }

  try {
    const parsed = new URL(`http://${candidate}`);
    return parsed.hostname ? parsed.hostname.toLowerCase() : null;
  } catch {
    return null;
  }
};

const addNormalizedHosts = (hosts: Set<string>, rawValue: string | undefined) => {
  if (!rawValue) {
    return;
  }

  for (const candidate of splitHostCandidates(rawValue)) {
    const normalized = normalizeHost(candidate);
    if (normalized) {
      hosts.add(normalized);
    }
  }
};

export const buildSsrAllowedHosts = (env: NodeJS.ProcessEnv): string[] => {
  const hosts = new Set<string>();

  addNormalizedHosts(hosts, env['NG_ALLOWED_HOSTS']);
  addNormalizedHosts(hosts, env['APP_DOMAIN']);
  addNormalizedHosts(hosts, env['APP_URL']);
  addNormalizedHosts(hosts, env['PUBLIC_URL']);
  addNormalizedHosts(hosts, env['FRONTEND_URL']);

  for (const localHost of LOCAL_ALLOWED_HOSTS) {
    hosts.add(localHost);
  }

  const runtimeHost = normalizeHost(env['HOST'] || '');
  if (runtimeHost && runtimeHost !== '0.0.0.0') {
    hosts.add(runtimeHost);
  }

  const hasConfiguredPublicHost = hosts.size > LOCAL_ALLOWED_HOSTS.length;
  if (!hasConfiguredPublicHost && runtimeHost === '0.0.0.0') {
    hosts.add('0.0.0.0');
  }

  return Array.from(hosts);
};
