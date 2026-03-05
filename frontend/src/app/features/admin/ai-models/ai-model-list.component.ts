import { CommonModule } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterModule } from '@angular/router';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import { ZardButtonComponent } from '@/shared/components/button';

interface AiModelItem {
  id: number;
  provider: string;
  model_id: string;
  name: string;
  description: string;
}

@Component({
  selector: 'app-ai-model-list',
  standalone: true,
  imports: [CommonModule, RouterModule, SearchToolbarComponent, ZardButtonComponent],
  templateUrl: './ai-model-list.component.html',
  styleUrls: ['./ai-model-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiModelListComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  readonly items = signal<AiModelItem[]>([]);
  readonly query = signal('');
  readonly loading = signal(false);

  ngOnInit(): void {
    this.load();
  }

  onQueryChange(value: string): void {
    this.query.set(value.trim());
    this.load();
  }

  createNew(): void {
    this.router.navigate(['/admin/ai-models/new']);
  }

  edit(item: AiModelItem): void {
    this.router.navigate(['/admin/ai-models', item.id, 'edit']);
  }

  private load(): void {
    let params = new HttpParams().set('ordering', 'provider,name');
    if (this.query()) params = params.set('search', this.query());
    this.loading.set(true);
    this.http.get<AiModelItem[]>('/api/ai-models/', { params }).subscribe({
      next: (rows) => {
        this.items.set(rows ?? []);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }
}
