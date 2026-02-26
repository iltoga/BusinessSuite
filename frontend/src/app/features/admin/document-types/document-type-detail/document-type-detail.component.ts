import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  inject,
  OnInit,
  PLATFORM_ID,
  signal,
} from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { DocumentTypesService } from '@/core/api';
import { DocumentType } from '@/core/api/model/document-type';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { CardSkeletonComponent, ZardSkeletonComponent } from '@/shared/components/skeleton';

@Component({
  selector: 'app-document-type-detail',
  standalone: true,
  imports: [
    CommonModule,
    ZardButtonComponent,
    ZardCardComponent,
    ZardBadgeComponent,
    CardSkeletonComponent,
    ZardSkeletonComponent,
  ],
  templateUrl: './document-type-detail.component.html',
  styleUrls: ['./document-type-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentTypeDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private documentTypesApi = inject(DocumentTypesService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);

  readonly documentType = signal<DocumentType | null>(null);
  readonly isLoading = signal(false);
  readonly originSearchQuery = signal<string | null>(null);

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    const item = this.documentType();
    if (!item) return;

    if (event.key === 'E' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.onEdit();
    }

    if (
      (event.key === 'B' || event.key === 'ArrowLeft') &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      event.preventDefault();
      this.onBack();
    }
  }

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }

    const st = (window as any).history.state || {};
    this.originSearchQuery.set(st.searchQuery ?? null);

    const idParam = this.route.snapshot.paramMap.get('id');
    const id = Number(idParam);
    if (!id || Number.isNaN(id)) {
      this.toast.error('Document type not found');
      this.onBack();
      return;
    }

    this.loadDocumentType(id);
  }

  onEdit(): void {
    const item = this.documentType();
    if (!item) return;

    this.router.navigate(['/admin/document-types'], {
      state: {
        focusTable: true,
        focusId: item.id,
        searchQuery: this.originSearchQuery(),
        openEditId: item.id,
      },
    });
  }

  onBack(): void {
    const item = this.documentType();
    this.router.navigate(['/admin/document-types'], {
      state: {
        focusTable: true,
        focusId: item?.id,
        searchQuery: this.originSearchQuery(),
      },
    });
  }

  yesNo(value?: boolean): string {
    return value ? 'Yes' : 'No';
  }

  badgeType(value?: boolean): 'success' | 'secondary' {
    return value ? 'success' : 'secondary';
  }

  private loadDocumentType(id: number): void {
    this.isLoading.set(true);
    this.documentTypesApi.documentTypesRetrieve(id).subscribe({
      next: (documentType) => {
        this.documentType.set(documentType);
        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load document type');
        this.isLoading.set(false);
        this.onBack();
      },
    });
  }
}
