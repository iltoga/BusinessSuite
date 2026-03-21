import { describe, expect, it } from 'vitest';

import {
  REQUEST_METADATA_CONTEXT,
  createAsyncRequestMetadata,
  createRequestMetadata,
  requestMetadataContext,
  requestMetadataHeaders,
} from './request-metadata';

describe('request-metadata utilities', () => {
  it('creates a request metadata object with a request id by default', () => {
    const metadata = createRequestMetadata();

    expect(metadata.requestId).toMatch(/^req_/);
    expect(metadata.idempotencyKey).toBeNull();
  });

  it('creates async request metadata with an idempotency key', () => {
    const metadata = createAsyncRequestMetadata();

    expect(metadata.requestId).toMatch(/^req_/);
    expect(metadata.idempotencyKey).toMatch(/^idem_/);
  });

  it('trims provided metadata values and omits blank idempotency keys from headers', () => {
    expect(
      requestMetadataHeaders({
        requestId: '  req-123  ',
        idempotencyKey: '   ',
      }),
    ).toEqual({
      'X-Request-ID': 'req-123',
    });
  });

  it('stores explicit metadata in a request context and generates one when omitted', () => {
    const explicitMetadata = {
      requestId: 'req-123',
      idempotencyKey: 'idem-456',
    };

    const explicitContext = requestMetadataContext(explicitMetadata);
    expect(explicitContext.get(REQUEST_METADATA_CONTEXT)).toEqual(explicitMetadata);

    const generatedContext = requestMetadataContext();
    const generatedMetadata = generatedContext.get(REQUEST_METADATA_CONTEXT);

    expect(generatedMetadata).not.toBeNull();
    expect(generatedMetadata?.requestId).toMatch(/^req_/);
  });
});
