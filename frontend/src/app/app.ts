import { ZardToastComponent } from '@/shared/components/toast';
import { isPlatformBrowser } from '@angular/common';
import { Component, HostListener, inject, PLATFORM_ID, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { HelpDrawerComponent, HotkeysDrawerComponent } from '@/shared/components/help-drawer';
import { HelpService } from '@/shared/services/help.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, ZardToastComponent, HelpDrawerComponent, HotkeysDrawerComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly platformId = inject(PLATFORM_ID);
  protected readonly title = signal('business-suite-frontend');
  protected readonly isBrowser = signal(isPlatformBrowser(this.platformId));

  protected readonly help = inject(HelpService);

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
