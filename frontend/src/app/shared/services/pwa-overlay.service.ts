import { isPlatformBrowser } from '@angular/common';
import { DestroyRef, inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';

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
  private readonly destroyRef = inject(DestroyRef);
  private readonly isBrowser = isPlatformBrowser(this.platformId);
  private readonly overlayMode = signal(false);
  readonly isOverlayMode = this.overlayMode.asReadonly();
  readonly isOverlayMode$ = toObservable(this.isOverlayMode);
  private readonly overlayMediaQuery = this.isBrowser
    ? window.matchMedia('(display-mode: window-controls-overlay)')
    : null;
  private readonly standaloneMediaQuery = this.isBrowser
    ? window.matchMedia('(display-mode: standalone)')
    : null;

  constructor() {
    if (!this.isBrowser) {
      return;
    }

    this.syncOverlayMode();

    const wco = navigator.windowControlsOverlay;
    if (wco) {
      wco.addEventListener('geometrychange', this.syncOverlayMode);
    }

    this.overlayMediaQuery?.addEventListener('change', this.syncOverlayMode);
    this.standaloneMediaQuery?.addEventListener('change', this.syncOverlayMode);

    this.destroyRef.onDestroy(() => {
      wco?.removeEventListener('geometrychange', this.syncOverlayMode);
      this.overlayMediaQuery?.removeEventListener('change', this.syncOverlayMode);
      this.standaloneMediaQuery?.removeEventListener('change', this.syncOverlayMode);
    });
  }

  private readonly syncOverlayMode = () => {
    if (!this.isBrowser) {
      this.overlayMode.set(false);
      return;
    }

    const overlayMedia = this.overlayMediaQuery?.matches ?? false;
    const standaloneMedia = this.standaloneMediaQuery?.matches ?? false;
    this.overlayMode.set(overlayMedia || standaloneMedia);
  };
}
