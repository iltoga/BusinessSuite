import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import type { ClassValue } from 'clsx';

import { ZardButtonComponent } from '@/shared/components/button';
import { ZardIconComponent } from '@/shared/components/icon';
import { mergeClasses } from '@/shared/utils/merge-classes';

@Component({
  selector: 'app-image-magnifier',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent, ZardIconComponent],
  templateUrl: './image-magnifier.component.html',
  styleUrls: ['./image-magnifier.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ImageMagnifierComponent {
  src = input<string | null | undefined>(null);
  alt = input<string>('Image preview');
  href = input<string | null | undefined>(null);
  imageClass = input<ClassValue>('');
  wrapperClass = input<ClassValue>('');
  toggleClass = input<ClassValue>('');
  lensSize = input<number>(200);
  zoom = input<number>(4);
  showToggle = input<boolean>(true);
  enabledByDefault = input<boolean>(false);

  readonly magnifierActive = signal(false);
  readonly magnifierLensX = signal(0);
  readonly magnifierLensY = signal(0);
  readonly magnifierBgX = signal(0);
  readonly magnifierBgY = signal(0);
  readonly magnifierEnabled = signal(false);

  readonly hasSource = computed(() => Boolean(this.src()?.trim()));
  readonly resolvedSrc = computed(() => this.src()?.trim() ?? '');
  readonly resolvedHref = computed(() => this.href()?.trim() ?? '');

  readonly resolvedWrapperClass = computed(() =>
    mergeClasses('image-magnifier-wrapper', this.wrapperClass()),
  );
  readonly resolvedImageClass = computed(() =>
    mergeClasses('image-magnifier-image', this.imageClass()),
  );
  readonly resolvedToggleClass = computed(() =>
    mergeClasses('image-magnifier-toggle h-8 w-8 shrink-0 p-0', this.toggleClass()),
  );

  constructor() {
    this.magnifierEnabled.set(this.enabledByDefault());
  }

  toggleMagnifier(): void {
    const enabled = !this.magnifierEnabled();
    this.magnifierEnabled.set(enabled);
    if (!enabled) {
      this.magnifierActive.set(false);
    }
  }

  onImageMouseEnter(): void {
    if (!this.magnifierEnabled()) {
      return;
    }
    this.magnifierActive.set(true);
  }

  onImageMouseLeave(): void {
    this.magnifierActive.set(false);
  }

  onImageMouseMove(event: MouseEvent): void {
    if (!this.magnifierEnabled()) {
      return;
    }

    const image = event.currentTarget as HTMLImageElement | null;
    if (!image) {
      return;
    }

    const rect = image.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      return;
    }

    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const clampedX = Math.max(0, Math.min(x, rect.width));
    const clampedY = Math.max(0, Math.min(y, rect.height));
    const halfLens = this.lensSize() / 2;

    this.magnifierLensX.set(clampedX - halfLens);
    this.magnifierLensY.set(clampedY - halfLens);
    this.magnifierBgX.set((clampedX / rect.width) * 100);
    this.magnifierBgY.set((clampedY / rect.height) * 100);
  }
}
