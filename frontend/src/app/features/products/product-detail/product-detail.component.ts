import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  PLATFORM_ID,
  signal,
  viewChild,
  type OnInit,
  type TemplateRef,
} from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import {
  ProductsService,
  type DocumentType,
  type ProductDetail,
  type TaskNested,
} from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import {
  DataTableComponent,
  type ColumnConfig,
} from '@/shared/components/data-table/data-table.component';

@Component({
  selector: 'app-product-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ZardButtonComponent,
    ZardCardComponent,
    ZardBadgeComponent,
    DataTableComponent,
  ],
  templateUrl: './product-detail.component.html',
  styleUrls: ['./product-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private productsApi = inject(ProductsService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);

  private readonly lastStepTemplate =
    viewChild.required<TemplateRef<{ $implicit: TaskNested; value: any; row: TaskNested }>>(
      'lastStepTemplate',
    );

  readonly product = signal<ProductDetail | null>(null);
  readonly isLoading = signal(false);

  readonly requiredDocuments = computed<DocumentType[]>(
    () => this.product()?.requiredDocumentTypes ?? [],
  );
  readonly optionalDocuments = computed<DocumentType[]>(
    () => this.product()?.optionalDocumentTypes ?? [],
  );

  readonly tasks = computed(() => {
    const items = this.product()?.tasks ?? [];
    return [...items].sort((a, b) => (a.step ?? 0) - (b.step ?? 0));
  });

  readonly taskColumns = computed<ColumnConfig<TaskNested>[]>(() => [
    { key: 'step', header: 'Step' },
    { key: 'name', header: 'Task' },
    { key: 'duration', header: 'Duration (days)' },
    { key: 'notifyDaysBefore', header: 'Notify (days)' },
    { key: 'lastStep', header: 'Last step', template: this.lastStepTemplate() },
  ]);

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    const idParam = this.route.snapshot.paramMap.get('id');
    if (!idParam) {
      return;
    }
    const id = Number(idParam);
    this.loadProduct(id);
  }

  productTypeLabel(type?: string | null): string {
    if (type === 'visa') return 'Visa';
    if (type === 'other') return 'Other';
    return type ?? '—';
  }

  private loadProduct(id: number): void {
    this.isLoading.set(true);
    this.productsApi.productsRetrieve(id).subscribe({
      next: (product) => {
        this.product.set(product);
        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load product');
        this.isLoading.set(false);
      },
    });
  }
}
