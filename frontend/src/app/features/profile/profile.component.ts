import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
  TemplateRef,
  viewChild,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';

import { UserProfileService } from '@/core/api/api/user-profile.service';
import { UserProfile } from '@/core/api/model/user-profile';
import { UserSettingsApiService } from '@/core/api/user-settings.service';
import { AuthService } from '@/core/services/auth.service';
import { DesktopBridgeService } from '@/core/services/desktop-bridge.service';
import { ThemeService } from '@/core/services/theme.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardAvatarComponent } from '@/shared/components/avatar';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardCheckboxComponent } from '@/shared/components/checkbox';
import { ZardDialogService } from '@/shared/components/dialog';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardCardComponent,
    ZardButtonComponent,
    ZardInputDirective,
    ZardAvatarComponent,
    ZardBadgeComponent,
    ZardCheckboxComponent,
    ZardIconComponent,
    AppDatePipe,
  ],
  templateUrl: './profile.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProfileComponent implements OnInit {
  private fb = inject(FormBuilder);
  private userProfileService = inject(UserProfileService);
  private authService = inject(AuthService);
  private desktopBridge = inject(DesktopBridgeService);
  private toast = inject(GlobalToastService);
  private dialogService = inject(ZardDialogService);

  readonly passwordModalTemplate = viewChild.required<TemplateRef<any>>('passwordModalTemplate');

  profile = signal<UserProfile | null>(null);
  isLoading = signal(true);
  isSaving = signal(false);

  // Theme related
  private themeService = inject(ThemeService);
  private userSettingsApi = inject(UserSettingsApiService);
  availableThemes = this.themeService.getAvailableThemes();
  currentTheme = this.themeService.currentTheme;
  isDesktopApp = signal(false);
  isLaunchAtLoginLoading = signal(false);
  isLaunchAtLoginUpdating = signal(false);
  launchAtLoginEnabled = signal(false);

  private dialogRef: any = null;

  profileForm = this.fb.nonNullable.group({
    firstName: ['', Validators.required],
    lastName: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
  });

  passwordForm = this.fb.nonNullable.group(
    {
      oldPassword: ['', Validators.required],
      newPassword: ['', [Validators.required, Validators.minLength(8)]],
      confirmPassword: ['', Validators.required],
    },
    {
      validators: (group) => {
        const pass = group.get('newPassword')?.value;
        const confirm = group.get('confirmPassword')?.value;
        return pass === confirm ? null : { notSame: true };
      },
    },
  );

  userInitials = computed(() => {
    const p = this.profile();
    if (!p) return 'U';
    const first = p.firstName?.[0] || '';
    const last = p.lastName?.[0] || '';
    return (first + last).toUpperCase() || p.username?.[0].toUpperCase() || 'U';
  });

  ngOnInit(): void {
    this.loadProfile();
    void this.loadDesktopPreferences();
    // Also attempt to load and apply user settings for display
    if (this.authService.isAuthenticated()) {
      this.userSettingsApi.getMe().subscribe({
        next: (s) => {
          if (s?.theme) {
            this.themeService.setTheme(s.theme as any);
          }
          // Accept either snake_case or camelCase keys from server
          const serverDark = (s as any)?.dark_mode ?? (s as any)?.darkMode;
          if (typeof serverDark === 'boolean') {
            this.themeService.setDarkMode(!!serverDark);
          }
        },
        error: () => {
          // non-blocking: ignore
        },
      });
    }
  }

  private async loadDesktopPreferences(): Promise<void> {
    const isDesktop = this.desktopBridge.isDesktop();
    this.isDesktopApp.set(isDesktop);
    if (!isDesktop) return;

    this.isLaunchAtLoginLoading.set(true);
    try {
      const enabled = await this.desktopBridge.getLaunchAtLogin();
      this.launchAtLoginEnabled.set(enabled);
    } finally {
      this.isLaunchAtLoginLoading.set(false);
    }
  }

  loadProfile(): void {
    this.isLoading.set(true);
    this.userProfileService
      .userProfileMeRetrieve()
      .pipe(finalize(() => this.isLoading.set(false)))
      .subscribe({
        next: (profile) => {
          this.profile.set(profile);
          this.authService.updateClaims({ avatar: profile.avatar });
          this.profileForm.patchValue({
            firstName: profile.firstName || '',
            lastName: profile.lastName || '',
            email: profile.email || '',
          });
        },
        error: () => {
          this.toast.error('Failed to load profile');
        },
      });
  }

  onAvatarSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files[0]) {
      const file = input.files[0];
      this.uploadAvatar(file);
    }
  }

  private uploadAvatar(file: File): void {
    this.isSaving.set(true);
    // The generated API expects avatar as the first positional argument
    this.userProfileService
      .userProfileUploadAvatarCreate(file as any)
      .pipe(finalize(() => this.isSaving.set(false)))
      .subscribe({
        next: (updated) => {
          this.profile.set(updated);
          this.authService.updateClaims({ avatar: updated.avatar });
          this.toast.success('Avatar updated successfully');
        },
        error: (err) => {
          this.toast.error(err.error?.detail || 'Failed to upload avatar');
        },
      });
  }

  onUpdateProfile(): void {
    const profile = this.profile();
    if (this.profileForm.invalid || !profile) return;

    const rawValues = this.profileForm.getRawValue();

    this.isSaving.set(true);
    this.userProfileService
      .userProfileUpdateProfilePartialUpdate(
        profile.id,
        profile.username,
        profile.fullName,
        profile.role,
        profile.avatar ?? '',
        profile.lastLogin ?? '',
        profile.isSuperuser,
        rawValues.email,
        rawValues.firstName,
        rawValues.lastName,
      )
      .pipe(finalize(() => this.isSaving.set(false)))
      .subscribe({
        next: (updated) => {
          this.profile.set(updated);
          this.authService.updateClaims({
            email: updated.email,
            fullName: updated.fullName,
            avatar: updated.avatar,
          });
          this.toast.success('Profile updated successfully');
        },
        error: (err) => {
          // Check for field-specific errors in the standardized format
          const errors = err.error?.errors || err.error;
          if (errors && typeof errors === 'object') {
            const fieldErrors = Object.entries(errors);
            if (fieldErrors.length > 0) {
              const [field, messages] = fieldErrors[0];
              if (Array.isArray(messages) && messages.length > 0) {
                this.toast.error(`${field}: ${messages[0]}`);
                return;
              }
            }
          }
          this.toast.error(err.error?.detail || 'Failed to update profile');
        },
      });
  }

  onChangePassword(): void {
    if (this.passwordForm.invalid) return;

    const { oldPassword, newPassword } = this.passwordForm.getRawValue();
    this.isSaving.set(true);
    this.userProfileService
      .userProfileChangePasswordCreate(oldPassword, newPassword)
      .pipe(finalize(() => this.isSaving.set(false)))
      .subscribe({
        next: () => {
          this.toast.success('Password changed successfully');
          this.closeChangePasswordModal();
        },
        error: (err) => {
          // Map backend errors to form
          if (err.error?.old_password) {
            this.passwordForm.get('oldPassword')?.setErrors({ backend: err.error.old_password[0] });
          }
          this.toast.error(err.error?.detail || 'Failed to change password');
        },
      });
  }

  onThemeChange(event: Event): void {
    const select = event.target as HTMLSelectElement;
    const theme = (select.value as any) || (this.currentTheme() as any);

    // Optimistic UI update
    this.themeService.setTheme(theme as any);

    // Persist to server if authenticated
    if (this.authService.isAuthenticated()) {
      this.userSettingsApi.patchMe({ theme }).subscribe({
        next: () => {
          this.toast.success('Theme updated');
        },
        error: (err) => {
          this.toast.error('Failed to save theme');
        },
      });
    }
  }

  formatThemeName(theme: string): string {
    return theme.charAt(0).toUpperCase() + theme.slice(1);
  }

  async onLaunchAtLoginToggle(): Promise<void> {
    if (!this.isDesktopApp() || this.isLaunchAtLoginUpdating() || this.isLaunchAtLoginLoading()) {
      return;
    }

    const nextValue = !this.launchAtLoginEnabled();
    this.isLaunchAtLoginUpdating.set(true);
    try {
      const enabled = await this.desktopBridge.setLaunchAtLogin(nextValue);
      this.launchAtLoginEnabled.set(enabled);
      this.toast.success(enabled ? 'Launch at login enabled' : 'Launch at login disabled');
    } catch {
      this.toast.error('Failed to update launch-at-login setting');
    } finally {
      this.isLaunchAtLoginUpdating.set(false);
    }
  }

  openChangePasswordModal(): void {
    this.passwordForm.reset();
    this.dialogRef = this.dialogService.create({
      zTitle: 'Change Password',
      zContent: this.passwordModalTemplate(),
      zHideFooter: true,
      zClosable: true,
    });
  }

  closeChangePasswordModal(): void {
    if (this.dialogRef) {
      this.dialogRef.close();
      this.dialogRef = null;
    }
  }
}
