import { LoggingService } from '@/core/services/logging.service';
import { ErrorHandler, Injectable, Injector } from '@angular/core';

@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  constructor(private injector: Injector) {}

  handleError(error: any): void {
    const logging = this.injector.get(LoggingService) as LoggingService;

    const payload = {
      level: 'ERROR',
      message: error?.message ? String(error.message) : String(error),
      stack: error?.stack ? String(error.stack) : null,
      metadata: {
        url: (typeof window !== 'undefined' && window.location && window.location.href) || null,
      },
    };

    try {
      logging.sendLog(payload);
    } catch (e) {
      // Ensure error handler never throws
      // eslint-disable-next-line no-console
      console.error('Failed to send log', e);
    }

    // still rethrow or log to console for developers
    // eslint-disable-next-line no-console
    console.error(error);
  }
}
