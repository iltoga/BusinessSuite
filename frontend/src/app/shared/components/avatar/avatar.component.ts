import { ZardIconComponent } from '@/shared/components/icon';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  signal,
  ViewEncapsulation,
} from '@angular/core';

import {
  avatarVariants,
  imageVariants,
  type ZardAvatarVariants,
  type ZardImageVariants,
} from './avatar.variants';

import { mergeClasses } from '@/shared/utils/merge-classes';

export type ZardAvatarStatus = 'online' | 'offline' | 'doNotDisturb' | 'away';

@Component({
  selector: 'z-avatar, [z-avatar]',
  standalone: true,
  imports: [ZardIconComponent],
  template: `
    @if (zFallback() && (!zSrc() || !imageLoaded())) {
      <span class="absolute z-0 m-auto text-base font-semibold text-foreground">{{
        zFallback()
      }}</span>
    }

    @if (zSrc() && !imageError()) {
      <img
        [src]="zSrc()"
        [alt]="zAlt()"
        [class]="imgClasses()"
        [hidden]="!imageLoaded()"
        (load)="onImageLoad()"
        (error)="onImageError()"
      />
    }

    @if (zStatus()) {
      @switch (zStatus()) {
        @case ('online') {
          <z-icon
            zType="circle"
            class="absolute -right-1.25 -bottom-1.25 z-20 h-5 w-5 text-green-500"
          />
        }
        @case ('offline') {
          <z-icon
            zType="circle"
            class="absolute -right-1.25 -bottom-1.25 z-20 h-5 w-5 text-red-500"
          />
        }
        @case ('doNotDisturb') {
          <z-icon
            zType="circle-x"
            class="absolute -right-1.25 -bottom-1.25 z-20 h-5 w-5 text-red-500"
          />
        }
        @case ('away') {
          <z-icon
            zType="moon"
            class="absolute -right-1.25 -bottom-1.25 z-20 h-5 w-5 text-yellow-400"
          />
        }
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
  host: {
    '[class]': 'containerClasses()',
    '[style.width]': 'customSize()',
    '[style.height]': 'customSize()',
    '[attr.data-slot]': '"avatar"',
    '[attr.data-status]': 'zStatus() ?? null',
  },
  exportAs: 'zAvatar',
})
export class ZardAvatarComponent {
  readonly zStatus = input<ZardAvatarStatus>();
  readonly zShape = input<ZardImageVariants['zShape']>('circle');
  readonly zSize = input<ZardAvatarVariants['zSize'] | number>('default');
  readonly zSrc = input<string>();
  readonly zAlt = input<string>('');
  readonly zFallback = input<string>('');

  readonly class = input<string>('');

  protected readonly imageError = signal(false);
  protected readonly imageLoaded = signal(false);

  protected readonly containerClasses = computed(() => {
    const size = this.zSize();
    const zSize = typeof size === 'number' ? undefined : (size as ZardAvatarVariants['zSize']);

    return mergeClasses(avatarVariants({ zShape: this.zShape(), zSize }), this.class());
  });

  protected readonly customSize = computed(() => {
    const size = this.zSize();
    return typeof size === 'number' ? `${size}px` : null;
  });

  protected readonly imgClasses = computed(() =>
    mergeClasses(imageVariants({ zShape: this.zShape() })),
  );

  protected onImageLoad(): void {
    this.imageLoaded.set(true);
    this.imageError.set(false);
  }

  protected onImageError(): void {
    this.imageError.set(true);
    this.imageLoaded.set(false);
  }
}
