import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ZardButtonComponent } from '@/shared/components/button';

@Component({
  selector: 'app-workflow-notifications',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent],
  templateUrl: './workflow-notifications.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkflowNotificationsComponent {
  private http = inject(HttpClient);
  readonly notifications = signal<any[]>([]);
  readonly loading = signal(false);

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.http.get<any>('/api/workflow-notifications/').subscribe({
      next: (res) => {
        this.notifications.set(res?.results ?? res ?? []);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  resend(id: number): void {
    this.http.post(`/api/workflow-notifications/${id}/resend/`, {}).subscribe(() => this.load());
  }

  cancel(id: number): void {
    this.http.post(`/api/workflow-notifications/${id}/cancel/`, {}).subscribe(() => this.load());
  }

  remove(id: number): void {
    this.http.delete(`/api/workflow-notifications/${id}/`).subscribe(() => this.load());
  }
}
