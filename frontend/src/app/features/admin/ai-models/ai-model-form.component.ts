import { CommonModule, isPlatformBrowser } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  PLATFORM_ID,
  signal,
} from '@angular/core';
import { ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { Observable } from 'rxjs';

import { ZardButtonComponent } from '@/shared/components/button';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { BaseFormComponent, BaseFormConfig } from '@/shared/core/base-form.component';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

interface OpenRouterModelResult {
  provider?: string;
  model_id?: string;
  modelId?: string;
  name?: string;
  description?: string;
  modality?: string;
  // Architecture
  architectureModality?: string;
  architectureTokenizer?: string;
  instructType?: string;
  // Capabilities
  vision?: boolean;
  fileUpload?: boolean;
  reasoning?: boolean;
  // Context and tokens
  contextLength?: number | null;
  maxCompletionTokens?: number | null;
  // Pricing
  promptPricePerToken?: string | number | null;
  completionPricePerToken?: string | number | null;
  imagePrice?: string | number | null;
  requestPrice?: string | number | null;
  // Provider info
  topProviderId?: string;
  providerName?: string;
  // Additional metadata
  supportedParameters?: string[];
  perRequestLimits?: any;
}

interface AiModelDto {
  provider: string;
  model_id: string;
  name: string;
  description: string;
  vision: boolean;
  file_upload: boolean;
  reasoning: boolean;
  context_length: number | null;
  max_completion_tokens: number | null;
  modality: string;
  architecture_modality: string;
  architecture_tokenizer: string;
  instruct_type: string;
  prompt_price_per_token: string;
  completion_price_per_token: string;
  image_price: string;
  request_price: string;
  top_provider_id: string;
  provider_name: string;
  supported_parameters: string[];
  per_request_limits: any;
  source: string;
  raw_metadata: any;
}

interface ModelOption extends ZardComboboxOption {
  model: OpenRouterModelResult;
}

/**
 * AI Model form component
 *
 * Extends BaseFormComponent to inherit common form patterns:
 * - Keyboard shortcuts (Ctrl/Cmd+S to save, Escape to cancel)
 * - Edit mode detection from route
 * - Server error handling
 * - Loading states
 */
@Component({
  selector: 'app-ai-model-form',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    RouterModule,
    ZardButtonComponent,
    ZardComboboxComponent,
  ],
  templateUrl: './ai-model-form.component.html',
  styleUrls: ['./ai-model-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiModelFormComponent extends BaseFormComponent<any, AiModelDto, AiModelDto> {
  private readonly http = inject(HttpClient);

  // AI Model-specific state
  readonly isEdit = signal(false);
  readonly saveError = signal<string | null>(null);
  readonly isLoadingModels = signal(false);
  readonly modelOptions = signal<ModelOption[]>([]);

  // Debounce timer for search
  private searchTimer: number | null = null;

  override readonly destroyRef = inject(DestroyRef);
  override readonly platformId = inject(PLATFORM_ID);
  override readonly isBrowser = isPlatformBrowser(this.platformId);

  override readonly form = this.fb.group({
    provider: ['openrouter', Validators.required],
    model_id: [''],
    name: ['', Validators.required],
    description: [''],
    vision: [false],
    file_upload: [false],
    reasoning: [false],
    context_length: [null as number | null],
    max_completion_tokens: [null as number | null],
    modality: [''],
    architecture_modality: [''],
    architecture_tokenizer: [''],
    instruct_type: [''],
    prompt_price_per_token: [''],
    completion_price_per_token: [''],
    image_price: [''],
    request_price: [''],
    top_provider_id: [''],
    provider_name: [''],
    supported_parameters: [[] as string[]],
    per_request_limits: [{} as any],
    source: ['manual'],
    raw_metadata: [{} as any],
  });

  constructor() {
    super();
    this.config = {
      entityType: 'admin/ai-models',
      entityLabel: 'AI Model',
    } as BaseFormConfig<any, AiModelDto, AiModelDto>;

    this.destroyRef.onDestroy(() => {
      if (this.searchTimer && this.isBrowser) {
        try {
          window.clearTimeout(this.searchTimer);
        } catch {
          try {
            clearTimeout(this.searchTimer as any);
          } catch {}
        }
      }
    });
  }

  /**
   * Build the AI model form
   */
  protected override buildForm() {
    return this.form;
  }

  /**
   * Load AI model for edit mode
   */
  protected override loadItem(id: number): Observable<any> {
    return this.http.get<any>(`/api/ai-models/${id}/`);
  }

  /**
   * Create DTO from form value - converts display prices (per 1M tokens) back to per-token for API
   */
  protected override createDto(): AiModelDto {
    const formValue = this.form.getRawValue();
    return {
      provider: formValue.provider ?? 'openrouter',
      model_id: formValue.model_id ?? '',
      name: formValue.name ?? '',
      description: formValue.description ?? '',
      vision: formValue.vision ?? false,
      file_upload: formValue.file_upload ?? false,
      reasoning: formValue.reasoning ?? false,
      context_length: formValue.context_length,
      max_completion_tokens: formValue.max_completion_tokens,
      modality: formValue.modality ?? '',
      architecture_modality: formValue.architecture_modality ?? '',
      architecture_tokenizer: formValue.architecture_tokenizer ?? '',
      instruct_type: formValue.instruct_type ?? '',
      // Convert from per-1M-tokens back to per-token for backend storage
      prompt_price_per_token: this.toPerTokenPrice(formValue.prompt_price_per_token ?? ''),
      completion_price_per_token: this.toPerTokenPrice(formValue.completion_price_per_token ?? ''),
      image_price: this.toPerTokenPrice(formValue.image_price ?? ''),
      request_price: this.toPerTokenPrice(formValue.request_price ?? ''),
      top_provider_id: formValue.top_provider_id ?? '',
      provider_name: formValue.provider_name ?? '',
      supported_parameters: formValue.supported_parameters ?? [],
      per_request_limits: formValue.per_request_limits ?? {},
      source: formValue.source ?? 'manual',
      raw_metadata: formValue.raw_metadata ?? {},
    };
  }

  /**
   * Update DTO from form value - converts display prices (per 1M tokens) back to per-token for API
   */
  protected override updateDto(): AiModelDto {
    const formValue = this.form.getRawValue();
    return {
      provider: formValue.provider ?? 'openrouter',
      model_id: formValue.model_id ?? '',
      name: formValue.name ?? '',
      description: formValue.description ?? '',
      vision: formValue.vision ?? false,
      file_upload: formValue.file_upload ?? false,
      reasoning: formValue.reasoning ?? false,
      context_length: formValue.context_length,
      max_completion_tokens: formValue.max_completion_tokens,
      modality: formValue.modality ?? '',
      architecture_modality: formValue.architecture_modality ?? '',
      architecture_tokenizer: formValue.architecture_tokenizer ?? '',
      instruct_type: formValue.instruct_type ?? '',
      // Convert from per-1M-tokens back to per-token for backend storage
      prompt_price_per_token: this.toPerTokenPrice(formValue.prompt_price_per_token ?? ''),
      completion_price_per_token: this.toPerTokenPrice(formValue.completion_price_per_token ?? ''),
      image_price: this.toPerTokenPrice(formValue.image_price ?? ''),
      request_price: this.toPerTokenPrice(formValue.request_price ?? ''),
      top_provider_id: formValue.top_provider_id ?? '',
      provider_name: formValue.provider_name ?? '',
      supported_parameters: formValue.supported_parameters ?? [],
      per_request_limits: formValue.per_request_limits ?? {},
      source: formValue.source ?? 'manual',
      raw_metadata: formValue.raw_metadata ?? {},
    };
  }

  /**
   * Helper to convert display price (per 1M tokens) back to per-token price for backend
   */
  private toPerTokenPrice(displayPrice: string): string {
    if (!displayPrice || displayPrice.trim() === '') {
      return '';
    }
    const per1M = Number(displayPrice);
    if (isNaN(per1M) || per1M === 0) {
      return '';
    }
    // Convert from per-1M-tokens to per-token
    return (per1M / 1000000).toString();
  }

  /**
   * Helper to convert per-token price to display price (per 1M tokens)
   */
  private toPer1MPrice(perTokenPrice: string | number | null | undefined): string {
    if (perTokenPrice === null || perTokenPrice === undefined || perTokenPrice === '') {
      return '';
    }
    const perToken = Number(perTokenPrice);
    if (isNaN(perToken)) {
      return '';
    }
    // Convert from per-token to per-1M-tokens
    return (perToken * 1000000).toFixed(2);
  }

  /**
   * Populate form with existing item data - converts per-token prices to per-1M-tokens for display
   */
  protected populateForm(item: any): void {
    this.form.patchValue({
      ...item,
      // Convert from per-token to per-1M-tokens for display
      prompt_price_per_token: this.toPer1MPrice(item.prompt_price_per_token),
      completion_price_per_token: this.toPer1MPrice(item.completion_price_per_token),
      image_price: this.toPer1MPrice(item.image_price),
      request_price: this.toPer1MPrice(item.request_price),
    });
  }

  /**
   * Save new AI model
   */
  protected override saveCreate(dto: AiModelDto): Observable<any> {
    return this.http.post('/api/ai-models/', dto);
  }

  /**
   * Update existing AI model
   */
  protected override saveUpdate(dto: AiModelDto): Observable<any> {
    return this.http.put(`/api/ai-models/${this.itemId!}/`, dto);
  }

  /**
   * Initialize component
   */
  override ngOnInit(): void {
    super.ngOnInit();

    const id = Number(this.route.snapshot.paramMap.get('id'));
    if (id > 0) {
      this.isEdit.set(true);
      this.isEditMode.set(true);
    }
  }

  /**
   * Search OpenRouter for models - called by combobox on search change
   */
  onModelSearchChange(query: string): void {
    if (!this.isBrowser) return;

    if (this.searchTimer) {
      try {
        window.clearTimeout(this.searchTimer);
      } catch {
        try {
          clearTimeout(this.searchTimer as any);
        } catch {}
      }
    }

    if (!query || query.trim().length === 0) {
      this.modelOptions.set([]);
      return;
    }

    this.searchTimer = window.setTimeout(() => {
      this.loadModels(query.trim());
    }, 300);
  }

  /**
   * Load models from OpenRouter API
   */
  private loadModels(query: string): void {
    this.isLoadingModels.set(true);
    const params = new HttpParams().set('q', query).set('limit', 10);
    this.http
      .get<{ results: OpenRouterModelResult[] }>('/api/ai-models/openrouter-search/', { params })
      .subscribe({
        next: (resp) => {
          const results = resp.results ?? [];
          this.modelOptions.set(
            results.map((result) => {
              const modelId = result.model_id ?? result.modelId ?? '';
              const name = result.name ?? modelId ?? 'Unknown Model';
              return {
                value: modelId,
                label: name,
                model: result,
              };
            }),
          );
          this.isLoadingModels.set(false);
        },
        error: () => {
          this.isLoadingModels.set(false);
          this.modelOptions.set([]);
        },
      });
  }

  /**
   * Handle model selection from combobox
   */
  onModelSelected(option: ZardComboboxOption): void {
    // Cast to ModelOption since we know it's our custom option type
    const modelOption = option as ModelOption;

    if (!modelOption || !modelOption.model) {
      return;
    }

    const result = modelOption.model;
    const modelId = result.model_id ?? result.modelId ?? '';

    // Convert pricing from per-token to per-1M-tokens for display
    // Note: API returns camelCase due to OpenAPI generator transformation
    const promptPrice =
      result.promptPricePerToken != null
        ? (Number(result.promptPricePerToken) * 1000000).toFixed(2)
        : '';
    const completionPrice =
      result.completionPricePerToken != null
        ? (Number(result.completionPricePerToken) * 1000000).toFixed(2)
        : '';
    const imagePrice =
      result.imagePrice != null ? (Number(result.imagePrice) * 1000000).toFixed(2) : '';
    const requestPrice =
      result.requestPrice != null ? (Number(result.requestPrice) * 1000000).toFixed(2) : '';

    console.log('[AI Model Form] Selected model:', {
      modelId,
      name: result.name,
      promptPricePerToken: result.promptPricePerToken,
      promptPricePer1M: promptPrice,
      completionPricePerToken: result.completionPricePerToken,
      completionPricePer1M: completionPrice,
      rawResult: result,
    });

    this.form.patchValue({
      provider: result.provider ?? 'openrouter',
      model_id: modelId,
      name: result.name ?? '',
      description: result.description ?? '',
      vision: result.vision ?? false,
      file_upload: result.fileUpload ?? false,
      reasoning: result.reasoning ?? false,
      context_length: result.contextLength ?? null,
      max_completion_tokens: result.maxCompletionTokens ?? null,
      modality: result.modality ?? '',
      architecture_modality: result.architectureModality ?? '',
      architecture_tokenizer: result.architectureTokenizer ?? '',
      instruct_type: result.instructType ?? '',
      prompt_price_per_token: promptPrice,
      completion_price_per_token: completionPrice,
      image_price: imagePrice,
      request_price: requestPrice,
      top_provider_id: result.topProviderId ?? '',
      provider_name: result.providerName ?? '',
      supported_parameters: result.supportedParameters ?? [],
      per_request_limits: result.perRequestLimits ?? {},
    });

    this.saveError.set(null);
  }

  /**
   * Save AI model - override to add custom error handling
   */
  override onSubmit(): void {
    this.form.markAllAsTouched();
    if (this.form.invalid) {
      this.toast.error('Please fill in all required fields before saving.');
      return;
    }

    this.saveError.set(null);
    this.isSaving.set(true);

    const payload = this.form.getRawValue();
    const id = this.itemId;
    const req = id
      ? this.http.put(`/api/ai-models/${id}/`, payload)
      : this.http.post('/api/ai-models/', payload);

    req.subscribe({
      next: () => {
        this.isSaving.set(false);
        this.toast.success('AI model saved successfully');
        this.router.navigate(['/admin/ai-models']);
      },
      error: (error) => {
        this.isSaving.set(false);
        const message = extractServerErrorMessage(error) || 'Unable to save AI model.';
        this.saveError.set(message);
        this.toast.error(message);
      },
    });
  }

  /**
   * Cancel and go back
   */
  override onCancel(): void {
    this.router.navigate(['/admin/ai-models']);
  }

  /**
   * Delete AI model
   */
  delete(): void {
    const id = this.itemId;
    if (!id) return;
    this.http.delete(`/api/ai-models/${id}/`).subscribe(() => {
      this.toast.success('AI model deleted successfully');
      this.router.navigate(['/admin/ai-models']);
    });
  }
}
