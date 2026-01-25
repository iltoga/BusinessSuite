import { ZardToastComponent } from '@/shared/components/toast';
import { isPlatformBrowser } from '@angular/common';
import { Component, inject, PLATFORM_ID, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, ZardToastComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly platformId = inject(PLATFORM_ID);
  protected readonly title = signal('business-suite-frontend');
  protected readonly isBrowser = signal(isPlatformBrowser(this.platformId));
}
