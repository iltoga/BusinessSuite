import { describe, expect, it } from 'vitest';

import { unwrapApiEnvelope, unwrapApiRecord } from './api-envelope';

describe('api-envelope utils', () => {
  it('unwraps canonical data envelopes', () => {
    expect(unwrapApiEnvelope({ data: { ok: true } })).toEqual({ ok: true });
    expect(unwrapApiRecord({ data: { foo: 'bar' } })).toEqual({ foo: 'bar' });
  });

  it('returns raw values when no envelope is present', () => {
    expect(unwrapApiEnvelope({ ok: true })).toEqual({ ok: true });
    expect(unwrapApiRecord({ ok: true })).toEqual({ ok: true });
  });

  it('returns null for non-object records', () => {
    expect(unwrapApiRecord(null)).toBeNull();
    expect(unwrapApiRecord('value')).toBeNull();
  });
});
