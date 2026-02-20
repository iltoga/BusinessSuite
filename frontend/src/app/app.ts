import { ZardToastComponent } from '@/shared/components/toast';
import { isPlatformBrowser } from '@angular/common';
import {
  ApplicationRef,
  Component,
  effect,
  HostListener,
  inject,
  NgZone,
  PLATFORM_ID,
  signal,
} from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { filter, take } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { PushNotificationsService } from '@/core/services/push-notifications.service';
import { ReminderDialogStackComponent } from '@/shared/components/reminder-dialog-stack/reminder-dialog-stack.component';
import { HelpDrawerComponent, HotkeysDrawerComponent } from '@/shared/components/help-drawer';
import { HelpService } from '@/shared/services/help.service';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    ZardToastComponent,
    ReminderDialogStackComponent,
    HelpDrawerComponent,
    HotkeysDrawerComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly appRef = inject(ApplicationRef);
  private readonly zone = inject(NgZone);
  private readonly authService = inject(AuthService);
  private readonly pushNotifications = inject(PushNotificationsService);
  protected readonly title = signal('business-suite-frontend');
  protected readonly isBrowser = signal(isPlatformBrowser(this.platformId));
  private readonly hydrationSettled = signal(false);

  protected readonly help = inject(HelpService);

  constructor() {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }

    this.appRef.isStable
      .pipe(
        filter((stable) => stable),
        take(1),
      )
      .subscribe(() => {
        this.hydrationSettled.set(true);
      });

    effect(() => {
      if (this.hydrationSettled() && this.authService.isAuthenticated()) {
        // Keep SW/FCM bootstrap outside Angular stability accounting.
        this.zone.runOutsideAngular(() => {
          void this.pushNotifications.initialize();
        });
      }
    });
  }

  // Zoneless-friendly global F1 handler: toggle help drawer and prevent default browser help
  @HostListener('window:keydown', ['$event'])
  onWindowKeydown(event: KeyboardEvent) {
    // Standardize F1 detection
    if (event.key === 'F1') {
      event.preventDefault();
      this.help.toggle();
      return;
    }

    // Shift+K opens the global hotkeys cheatsheet (case-insensitive)
    if (
      (event.key || '').toUpperCase() === 'K' &&
      event.shiftKey &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      event.preventDefault();
      this.help.toggleCheatsheet();
      return;
    }
  }
}
