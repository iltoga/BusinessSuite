import { HttpInterceptorFn } from '@angular/common/http';

import { createRequestMetadata, REQUEST_METADATA_CONTEXT } from '@/core/utils/request-metadata';

export const requestMetadataInterceptor: HttpInterceptorFn = (req, next) => {
  const metadata = req.context.get(REQUEST_METADATA_CONTEXT) ?? createRequestMetadata();
  let headers = req.headers;

  if (!headers.has('X-Request-ID')) {
    headers = headers.set('X-Request-ID', metadata.requestId);
  }

  if (metadata.idempotencyKey && !headers.has('Idempotency-Key')) {
    headers = headers.set('Idempotency-Key', metadata.idempotencyKey);
  }

  return next(headers === req.headers ? req : req.clone({ headers }));
};
