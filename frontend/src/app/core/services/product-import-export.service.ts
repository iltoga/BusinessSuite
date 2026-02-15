import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, switchMap, timer } from 'rxjs';

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
    return this.http.post<ProductImportExportStartResponse>('/api/products/import/start/', formData);
  }

  downloadExport(jobId: string): Observable<HttpResponse<Blob>> {
    return this.http.get(`/api/products/export/download/${jobId}/`, {
      observe: 'response',
      responseType: 'blob',
    });
  }

  pollJob(jobId: string): Observable<any> {
    return timer(0, 1000).pipe(switchMap(() => this.http.get(`/api/async-jobs/${jobId}/`)));
  }
}
