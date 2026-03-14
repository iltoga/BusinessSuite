import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

interface ProductImportExportStartResponse {
  job_id: string;
  status: string;
  progress: number;
}

@Injectable({
  providedIn: 'root',
})
export class ProductImportExportService {
  constructor(private http: HttpClient) {}

  startExport(searchQuery?: string): Observable<ProductImportExportStartResponse> {
    return this.http.post<ProductImportExportStartResponse>('/api/products/export/start/', {
      search_query: searchQuery ?? '',
    });
  }

  startImport(file: File): Observable<ProductImportExportStartResponse> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<ProductImportExportStartResponse>(
      '/api/products/import/start/',
      formData,
    );
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
