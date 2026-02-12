import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  HostListener,
  inject,
  PLATFORM_ID,
  signal,
  viewChild,
  type OnInit,
  type TemplateRef,
} from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

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
import {
  CardSkeletonComponent,
  TableSkeletonComponent,
  ZardSkeletonComponent,
} from '@/shared/components/skeleton';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { HelpService } from '@/shared/services/help.service';

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
    CardSkeletonComponent,
    TableSkeletonComponent,
    ZardSkeletonComponent,
    AppDatePipe,
  ],
  templateUrl: './product-detail.component.html',
  styleUrls: ['./product-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private productsApi = inject(ProductsService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);
  private help = inject(HelpService);

  private readonly lastStepTemplate =
    viewChild.required<TemplateRef<{ $implicit: TaskNested; value: any; row: TaskNested }>>(
      'lastStepTemplate',
    );

  readonly product = signal<ProductDetail | null>(null);
  readonly isLoading = signal(false);
  readonly originSearchQuery = signal<string | null>(null);

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

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    const product = this.product();
    if (!product) return;

    // E --> Edit
    if (event.key === 'E' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.router.navigate(['/products', product.id, 'edit'], {
        state: { from: 'products', focusId: product.id, searchQuery: this.originSearchQuery() },
      });
    }

    // B or Left Arrow --> Back to list
    if (
      (event.key === 'B' || event.key === 'ArrowLeft') &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      event.preventDefault();
      this.router.navigate(['/products'], {
        state: {
          focusTable: true,
          focusId: product.id,
          searchQuery: this.originSearchQuery(),
        },
      });
    }
  }

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    const st = (window as any).history.state || {};
    this.originSearchQuery.set(st.searchQuery ?? null);
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

        // Update contextual help for this specific product
        this.help.setContext({
          id: `/products/${id}`,
          briefExplanation: `Product: ${product.name || product.id}. Manage pricing, required documents, and workflow steps.`,
          details:
            'Edit pricing, required documents, and workflow steps. Use the task list to define the application workflow for this product.',
        });
      },
      error: () => {
        this.toast.error('Failed to load product');
        this.isLoading.set(false);
      },
    });
  }
}
