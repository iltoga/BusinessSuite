import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { SseService } from '@/core/services/sse.service';
import {
  createAsyncRequestMetadata,
  type RequestMetadata,
} from '@/core/utils/request-metadata';

export interface MediaCleanupStreamFile {
  path: string;
  sizeBytes?: number;
}

export interface MediaCleanupStreamEvent {
  event:
    | 'media_cleanup_started'
    | 'media_cleanup_progress'
    | 'media_cleanup_found'
    | 'media_cleanup_finished'
    | 'media_cleanup_failed';
  message?: string;
  error?: string;
  dryRun?: boolean;
  prefixes?: string[];
  scannedFiles?: number;
  referencedFiles?: number;
  orphanedFiles?: number;
  deletedFiles?: number;
  totalOrphanBytes?: number;
  errors?: string[];
  currentPrefix?: string;
  file?: MediaCleanupStreamFile;
  cleanup?: unknown;
  storage?: {
    backend?: string;
    provider?: string;
  };
}

@Injectable({
  providedIn: 'root',
})
export class ServerManagementMediaCleanupStreamService {
  private readonly sseService = inject(SseService);

  connect(dryRun: boolean, requestMetadata?: RequestMetadata | null): Observable<MediaCleanupStreamEvent> {
    const params = new URLSearchParams({
      dry_run: dryRun ? '1' : '0',
    });
    return this.sseService.connect<MediaCleanupStreamEvent>(
      `/api/server-management/media-cleanup/stream/?${params.toString()}`,
      {
        useReplayCursor: false,
        requestMetadata: requestMetadata ?? createAsyncRequestMetadata(),
      },
    );
  }
}
