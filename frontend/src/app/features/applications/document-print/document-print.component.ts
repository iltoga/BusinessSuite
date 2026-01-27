import { CommonModule, DatePipe, Location } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal, type OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

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
    DatePipe,
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

  readonly document = signal<DocumentPrintData | null>(null);
  readonly isLoading = signal(true);
  readonly error = signal<string | null>(null);
  readonly today = new Date();

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
}
