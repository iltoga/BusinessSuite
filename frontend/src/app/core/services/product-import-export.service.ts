import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { normalizeJobEnvelope } from '@/core/utils/async-job-contract';
import {
  createAsyncRequestMetadata,
  requestMetadataContext,
  type RequestMetadata,
} from '@/core/utils/request-metadata';

interface ProductImportExportStartResponse {
  jobId: string;
  status: string;
  progress: number;
  queued?: boolean;
  deduplicated?: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class ProductImportExportService {
  constructor(private http: HttpClient) {}

  startExport(
    searchQuery?: string,
    requestMetadata?: RequestMetadata | null,
  ): Observable<ProductImportExportStartResponse> {
    const metadata = requestMetadata ?? createAsyncRequestMetadata();
    return this.http
      .post<ProductImportExportStartResponse>(
        '/api/products/export/start/',
        {
          search_query: searchQuery ?? '',
        },
        {
          context: requestMetadataContext(metadata),
        },
      )
      .pipe(map((response) => normalizeJobEnvelope(response)));
  }

  startImport(
    file: File,
    requestMetadata?: RequestMetadata | null,
  ): Observable<ProductImportExportStartResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const metadata = requestMetadata ?? createAsyncRequestMetadata();
    return this.http
      .post<ProductImportExportStartResponse>('/api/products/import/start/', formData, {
        context: requestMetadataContext(metadata),
      })
      .pipe(map((response) => normalizeJobEnvelope(response)));
  }

  downloadExport(jobId: string): Observable<HttpResponse<Blob>> {
    return this.http.get(`/api/products/export/download/${jobId}/`, {
      observe: 'response',
      responseType: 'blob',
    });
  }

  // Manual HttpClient call – the generated OpenAPI client sends Accept: application/json
  // for binary endpoints, which breaks PDF downloads.
  downloadPriceListPdf(jobId: string): Observable<Blob> {
    return this.http.get(`/api/products/price-list/print/download/${jobId}/`, {
      responseType: 'blob',
    });
  }
}
