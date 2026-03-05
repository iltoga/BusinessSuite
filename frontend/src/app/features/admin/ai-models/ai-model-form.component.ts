import { CommonModule } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

interface OpenRouterModelResult {
  provider?: string;
  model_id?: string;
  modelId?: string;
  name?: string;
  description?: string;
  modality?: string;
}

@Component({
  selector: 'app-ai-model-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterModule, ZardButtonComponent],
  templateUrl: './ai-model-form.component.html',
  styleUrls: ['./ai-model-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiModelFormComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly toast = inject(GlobalToastService);

  readonly isEdit = signal(false);
  readonly modelId = signal<number | null>(null);
  readonly searchResults = signal<OpenRouterModelResult[]>([]);
  readonly isSaving = signal(false);
  readonly saveError = signal<string | null>(null);

  readonly form = this.fb.group({
    provider: ['openrouter', Validators.required],
    model_id: ['', Validators.required],
    name: ['', Validators.required],
    description: [''],
    vision: [false],
    file_upload: [false],
    reasoning: [false],
    context_length: [null as number | null],
    max_completion_tokens: [null as number | null],
    modality: [''],
    prompt_price_per_token: [''],
    completion_price_per_token: [''],
    image_price: [''],
    request_price: [''],
    source: ['manual'],
    raw_metadata: [{} as any],
  });

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    if (id > 0) {
      this.isEdit.set(true);
      this.modelId.set(id);
      this.http.get<any>(`/api/ai-models/${id}/`).subscribe((row) => this.form.patchValue(row));
    }
  }

  searchOpenRouter(event: Event): void {
    const q = (event.target as HTMLInputElement).value.trim();
    if (!q) {
      this.searchResults.set([]);
      return;
    }
    const params = new HttpParams().set('q', q).set('limit', 10);
    this.http.get<{ results: OpenRouterModelResult[] }>('/api/ai-models/openrouter-search/', { params }).subscribe((resp) => {
      this.searchResults.set(resp.results ?? []);
    });
  }

  useResult(row: OpenRouterModelResult): void {
    const modelId = row.model_id ?? row.modelId ?? '';
    this.form.patchValue({
      provider: row.provider ?? this.form.controls.provider.value,
      model_id: modelId,
      name: row.name ?? '',
      description: row.description ?? '',
      modality: row.modality ?? '',
    });
    this.form.controls.model_id.markAsTouched();
    this.saveError.set(null);
  }

  save(): void {
    this.form.markAllAsTouched();
    if (this.form.invalid) {
      this.toast.error('Please fill in all required fields before saving.');
      return;
    }

    this.saveError.set(null);
    this.isSaving.set(true);

    const payload = this.form.getRawValue();
    const id = this.modelId();
    const req = id ? this.http.put(`/api/ai-models/${id}/`, payload) : this.http.post('/api/ai-models/', payload);
    req.subscribe({
      next: () => {
        this.isSaving.set(false);
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

  delete(): void {
    const id = this.modelId();
    if (!id) return;
    this.http.delete(`/api/ai-models/${id}/`).subscribe(() => this.router.navigate(['/admin/ai-models']));
  }
}
