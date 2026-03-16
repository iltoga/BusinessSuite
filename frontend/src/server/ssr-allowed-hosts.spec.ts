import { describe, expect, it } from 'vitest';

import { buildSsrAllowedHosts } from './ssr-allowed-hosts';

describe('buildSsrAllowedHosts', () => {
  it('includes configured public hosts and local defaults', () => {
    const hosts = buildSsrAllowedHosts({
      APP_DOMAIN: 'crm.revisbali.com',
      HOST: '0.0.0.0',
      NODE_ENV: 'production',
    });

    expect(hosts).toContain('crm.revisbali.com');
    expect(hosts).toContain('localhost');
    expect(hosts).toContain('127.0.0.1');
    expect(hosts).not.toContain('0.0.0.0');
  });

  it('normalizes comma-separated hosts, urls, and wildcards', () => {
    const hosts = buildSsrAllowedHosts({
      NG_ALLOWED_HOSTS: ' https://crm.revisbali.com:443 , *.revisbali.com ; http://127.0.0.1:4200 ',
      HOST: '0.0.0.0',
    });

    expect(hosts).toContain('crm.revisbali.com');
    expect(hosts).toContain('*.revisbali.com');
    expect(hosts).toContain('127.0.0.1');
    expect(hosts).not.toContain('0.0.0.0');
  });

  it('allows 0.0.0.0 only for local fallback when no public host is configured', () => {
    const hosts = buildSsrAllowedHosts({
      HOST: '0.0.0.0',
    });

    expect(hosts).toContain('0.0.0.0');
  });
});
