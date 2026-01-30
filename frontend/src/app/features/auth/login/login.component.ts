import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService, LoginCredentials } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardInputDirective } from '@/shared/components/input';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardButtonComponent,
    ZardInputDirective,
    FormErrorSummaryComponent,
  ],
  template: `
    <form [formGroup]="loginForm" (ngSubmit)="onSubmit()" class="space-y-6">
      <app-form-error-summary [form]="loginForm" [labels]="formErrorLabels" />

      <div class="space-y-2">
        <h2 class="text-2xl font-semibold">Login</h2>
        <p class="text-sm text-muted-foreground">Use your admin credentials to sign in.</p>
      </div>

      <div class="space-y-4">
        <div class="space-y-2">
          <label for="username" class="text-sm font-medium">Username</label>
          <input
            id="username"
            type="text"
            z-input
            formControlName="username"
            placeholder="Enter username"
          />
        </div>

        <div class="space-y-2">
          <label for="password" class="text-sm font-medium">Password</label>
          <input
            id="password"
            type="password"
            z-input
            formControlName="password"
            placeholder="Enter password"
          />
        </div>
      </div>

      <button
        type="submit"
        z-button
        zFull
        [zLoading]="authService.isLoading()"
        [zDisabled]="authService.isLoading() || loginForm.invalid"
      >
        Login
      </button>

      @if (authService.error()) {
        <div class="text-sm text-destructive">
          {{ authService.error() }}
        </div>
      }
    </form>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent {
  private fb = inject(FormBuilder);
  authService = inject(AuthService);
  private router = inject(Router);
  private toast = inject(GlobalToastService);

  loginForm: FormGroup = this.fb.group({
    username: ['', Validators.required],
    password: ['', Validators.required],
  });

  readonly formErrorLabels: Record<string, string> = {
    username: 'Username',
    password: 'Password',
  };

  onSubmit(): void {
    if (this.loginForm.valid) {
      const credentials: LoginCredentials = this.loginForm.value;
      this.authService.login(credentials).subscribe({
        next: () => {
          this.toast.success('Login successful');
          this.router.navigate(['/dashboard']);
        },
        error: (error) => {
          applyServerErrorsToForm(this.loginForm, error);
          this.loginForm.markAllAsTouched();
          const message = extractServerErrorMessage(error);
          this.toast.error(message ? `Login failed: ${message}` : 'Invalid credentials');
        },
      });
    }
  }
}
