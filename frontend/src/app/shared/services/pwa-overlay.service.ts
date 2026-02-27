import { isPlatformBrowser } from '@angular/common';
import { inject, Injectable, PLATFORM_ID } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

declare global {
  interface WindowControlsOverlay extends EventTarget {
    visible: boolean;
  }

  interface Navigator {
    windowControlsOverlay?: WindowControlsOverlay;
  }
}

@Injectable({ providedIn: 'root' })
export class PwaOverlayService {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly isBrowser = isPlatformBrowser(this.platformId);
  private readonly overlayModeSubject = new BehaviorSubject<boolean>(false);
  readonly isOverlayMode$: Observable<boolean> = this.overlayModeSubject.asObservable();

  constructor() {
    if (!this.isBrowser) {
      return;
    }

    this.syncOverlayMode();

    const wco = navigator.windowControlsOverlay;
    if (wco) {
      wco.addEventListener('geometrychange', this.syncOverlayMode);
    }

    window
      .matchMedia('(display-mode: window-controls-overlay)')
      .addEventListener('change', this.syncOverlayMode);
    window
      .matchMedia('(display-mode: standalone)')
      .addEventListener('change', this.syncOverlayMode);
  }

  private readonly syncOverlayMode = () => {
    if (!this.isBrowser) {
      this.overlayModeSubject.next(false);
      return;
    }

    const overlayMedia = window.matchMedia('(display-mode: window-controls-overlay)').matches;
    const standaloneMedia = window.matchMedia('(display-mode: standalone)').matches;
    this.overlayModeSubject.next(overlayMedia || standaloneMedia);
  };
}
