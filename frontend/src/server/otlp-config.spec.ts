import { describe, expect, it } from 'vitest';

import { resolveOtlpTracesConfig } from './otlp-config';

describe('resolveOtlpTracesConfig', () => {
  it('prefers explicit traces endpoint and merges global plus traces headers', () => {
    const config = resolveOtlpTracesConfig({
      OTEL_TRACES_EXPORTER: 'otlp',
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: 'http://collector:4318/v1/traces',
      OTEL_EXPORTER_OTLP_HEADERS: 'X-Global=one,Authorization=Bearer global',
      OTEL_EXPORTER_OTLP_TRACES_HEADERS: 'X-Trace=two,Authorization=Bearer trace',
      OTEL_EXPORTER_OTLP_TRACES_TIMEOUT: '2500',
    });

    expect(config.enabled).toBe(true);
    expect(config.source).toBe('explicit-traces-endpoint');
    expect(config.endpoint).toBe('http://collector:4318/v1/traces');
    expect(config.headers).toEqual({
      Authorization: 'Bearer trace',
      'X-Global': 'one',
      'X-Trace': 'two',
    });
    expect(config.timeoutMs).toBe(2500);
  });

  it('falls back to Grafana Cloud endpoint and derives basic auth header', () => {
    const config = resolveOtlpTracesConfig({
      OTEL_TRACES_EXPORTER: 'otlp',
      GRAFANA_CLOUD_OTLP_ENDPOINT: 'https://otlp-gateway-prod.grafana.net/otlp',
      GRAFANA_CLOUD_OTLP_USER: '123',
      GRAFANA_CLOUD_OTLP_API_KEY: 'secret-key',
    });

    expect(config.enabled).toBe(true);
    expect(config.source).toBe('grafana-cloud-endpoint');
    expect(config.endpoint).toBe('https://otlp-gateway-prod.grafana.net/otlp/v1/traces');
    expect(config.headers['Authorization']).toBe(`Basic ${btoa('123:secret-key')}`);
    expect(config.timeoutMs).toBe(10000);
  });

  it('disables tracing when exporter is none', () => {
    const config = resolveOtlpTracesConfig({
      OTEL_TRACES_EXPORTER: 'none',
      GRAFANA_CLOUD_OTLP_ENDPOINT: 'https://otlp-gateway-prod.grafana.net/otlp',
    });

    expect(config.enabled).toBe(false);
    expect(config.endpoint).toBe('https://otlp-gateway-prod.grafana.net/otlp/v1/traces');
  });
});
