import { HttpContext, HttpHeaders, HttpRequest, HttpResponse } from '@angular/common/http';
import { firstValueFrom, of } from 'rxjs';

import { requestMetadataInterceptor } from '@/core/interceptors/request-metadata.interceptor';
import { REQUEST_METADATA_CONTEXT } from '@/core/utils/request-metadata';

describe('requestMetadataInterceptor', () => {
  it('injects request metadata headers from the request context', async () => {
    const request = new HttpRequest('POST', '/api/test', null, {
      context: new HttpContext().set(REQUEST_METADATA_CONTEXT, {
        requestId: 'req-123',
        idempotencyKey: 'idem-456',
      }),
    });

    let forwardedRequest: HttpRequest<unknown> | null = null;
    const response$ = requestMetadataInterceptor(request, (nextRequest) => {
      forwardedRequest = nextRequest;
      return of(new HttpResponse({ status: 200, body: {} }));
    });

    await firstValueFrom(response$);

    if (!forwardedRequest) {
      throw new Error('Expected request metadata interceptor to forward the request');
    }

    const forwarded = forwardedRequest as HttpRequest<unknown>;
    expect(forwarded.headers.get('X-Request-ID')).toBe('req-123');
    expect(forwarded.headers.get('Idempotency-Key')).toBe('idem-456');
  });

  it('generates a request id when the request context is missing', async () => {
    const request = new HttpRequest('POST', '/api/test', null);

    let forwardedRequest: HttpRequest<unknown> | null = null;
    const response$ = requestMetadataInterceptor(request, (nextRequest) => {
      forwardedRequest = nextRequest;
      return of(new HttpResponse({ status: 200, body: {} }));
    });

    await firstValueFrom(response$);

    if (!forwardedRequest) {
      throw new Error('Expected request metadata interceptor to forward the request');
    }

    const forwarded = forwardedRequest as HttpRequest<unknown>;
    expect(forwarded.headers.get('X-Request-ID')).toMatch(/^req_/);
    expect(forwarded.headers.has('Idempotency-Key')).toBe(false);
  });

  it('preserves request headers that already exist on the request', async () => {
    const request = new HttpRequest('POST', '/api/test', null, {
      context: new HttpContext().set(REQUEST_METADATA_CONTEXT, {
        requestId: 'req-123',
        idempotencyKey: 'idem-456',
      }),
      headers: new HttpHeaders({
        'X-Request-ID': 'existing-request-id',
        'Idempotency-Key': 'existing-idempotency-key',
      }),
    });

    let forwardedRequest: HttpRequest<unknown> | null = null;
    const response$ = requestMetadataInterceptor(request, (nextRequest) => {
      forwardedRequest = nextRequest;
      return of(new HttpResponse({ status: 200, body: {} }));
    });

    await firstValueFrom(response$);

    if (!forwardedRequest) {
      throw new Error('Expected request metadata interceptor to forward the request');
    }

    const forwarded = forwardedRequest as HttpRequest<unknown>;
    expect(forwarded).toBe(request);
    expect(forwarded.headers.get('X-Request-ID')).toBe('existing-request-id');
    expect(forwarded.headers.get('Idempotency-Key')).toBe('existing-idempotency-key');
  });
});
