import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { ZardCardComponent } from '@/shared/components/card';

@Component({
  selector: 'app-auth-layout',
  standalone: true,
  imports: [CommonModule, RouterOutlet, ZardCardComponent],
  template: `
    <div class="flex min-h-screen items-center justify-center bg-muted px-4">
      <z-card class="w-full max-w-md p-6">
        <router-outlet />
      </z-card>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuthLayoutComponent {}
