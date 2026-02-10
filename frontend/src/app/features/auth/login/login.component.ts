import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, OnInit } from '@angular/core';
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
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent implements OnInit {
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

  ngOnInit() {
    // If already authenticated (e.g. mock auth auto-login), redirect to dashboard
    if (this.authService.isAuthenticated()) {
      this.router.navigate(['/dashboard']);
    }
  }

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
