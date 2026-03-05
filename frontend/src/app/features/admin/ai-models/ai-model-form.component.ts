import { CommonModule } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { ZardButtonComponent } from '@/shared/components/button';

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

  readonly isEdit = signal(false);
  readonly modelId = signal<number | null>(null);
  readonly searchResults = signal<any[]>([]);

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
    this.http.get<{ results: any[] }>('/api/ai-models/openrouter-search/', { params }).subscribe((resp) => {
      this.searchResults.set(resp.results ?? []);
    });
  }

  useResult(row: any): void {
    this.form.patchValue(row);
  }

  save(): void {
    const payload = this.form.getRawValue();
    const id = this.modelId();
    const req = id ? this.http.put(`/api/ai-models/${id}/`, payload) : this.http.post('/api/ai-models/', payload);
    req.subscribe(() => this.router.navigate(['/admin/ai-models']));
  }

  delete(): void {
    const id = this.modelId();
    if (!id) return;
    this.http.delete(`/api/ai-models/${id}/`).subscribe(() => this.router.navigate(['/admin/ai-models']));
  }
}
