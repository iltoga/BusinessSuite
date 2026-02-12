import { CommonModule, Location } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, Router } from '@angular/router';

import { ConfigService } from '@/core/services/config.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

interface DocumentPrintData {
  id: number;
  docType: {
    name: string;
    hasOcrCheck: boolean;
  };
  docApplication: {
    id: number;
    customer: {
      fullName: string;
    };
    product: {
      name: string;
    };
  };
  docNumber?: string | null;
  expirationDate?: string | null;
  details?: string | null;
  fileLink?: string | null;
  ocrCheck: boolean;
  completed: boolean;
}

@Component({
  selector: 'app-document-print',
  standalone: true,
  imports: [
    CommonModule,
    ZardBadgeComponent,
    ZardButtonComponent,
    ZardCardComponent,
    AppDatePipe,
  ],
  templateUrl: './document-print.component.html',
  styleUrls: ['./document-print.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentPrintComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private location = inject(Location);
  private http = inject(HttpClient);
  private sanitizer = inject(DomSanitizer);
  private destroyRef = inject(DestroyRef);
  private configService = inject(ConfigService);

  readonly document = signal<DocumentPrintData | null>(null);
  readonly isLoading = signal(true);
  readonly error = signal<string | null>(null);
  readonly today = new Date();

  // PDF preview for print view
  readonly isPreviewLoading = signal(false);
  readonly previewError = signal<string | null>(null);
  readonly previewUrl = signal<string | null>(null);
  readonly sanitizedPreview = signal<SafeResourceUrl | null>(null);

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('documentId'));
    if (!id) {
      this.error.set('Invalid document ID');
      this.isLoading.set(false);
      return;
    }
    this.loadDocument(id);
  }

  private loadDocument(id: number): void {
    this.http.get<any>(`/api/documents/${id}/print/`).subscribe({
      next: (data) => {
        this.document.set(data);
        this.isLoading.set(false);

        // If file is PDF, try to fetch a blob and create a preview iframe/object
        if (data.fileLink && this.isPdf(data.fileLink)) {
          this.loadPdfPreview(data.fileLink);
        }
      },
      error: (err) => {
        this.error.set('Failed to load document');
        this.isLoading.set(false);
      },
    });
  }

  print(): void {
    window.print();
  }

  // Brand logo used in print view
  get logoSrc(): string {
    return '/assets/logo_transparent.png';
  }

  goBack(): void {
    const doc = this.document();
    if (doc) {
      // Use replaceUrl: true to avoid adding the print view to history
      this.router.navigate(['/applications', doc.docApplication.id], { replaceUrl: true });
    } else {
      this.location.back();
    }
  }

  isPdf(url: string): boolean {
    return url.toLowerCase().endsWith('.pdf');
  }

  private loadPdfPreview(url: string): void {
    this.isPreviewLoading.set(true);
    this.previewError.set(null);

    this.http.get(url, { responseType: 'blob' }).subscribe({
      next: (blob) => {
        try {
          const objectUrl = URL.createObjectURL(blob);
          this.previewUrl.set(objectUrl);
          this.sanitizedPreview.set(this.sanitizer.bypassSecurityTrustResourceUrl(objectUrl));
        } catch (e) {
          this.previewError.set('Failed to create preview.');
        } finally {
          this.isPreviewLoading.set(false);
        }
      },
      error: () => {
        this.previewError.set('Failed to load PDF for preview.');
        this.isPreviewLoading.set(false);
      },
    });

    this.destroyRef.onDestroy(() => {
      const url = this.previewUrl();
      if (url && url.startsWith('blob:')) {
        try {
          URL.revokeObjectURL(url);
        } catch (e) {}
      }
    });
  }
}
