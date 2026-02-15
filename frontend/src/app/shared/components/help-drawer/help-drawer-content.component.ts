import { ZardButtonComponent } from '@/shared/components/button/button.component';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import { ZardSkeletonComponent } from '@/shared/components/skeleton/skeleton.component';
import { HelpService } from '@/shared/services/help.service';
import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  ViewEncapsulation,
} from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';
import { marked } from 'marked';

@Component({
  selector: 'z-help-drawer-content',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent, ZardIconComponent, ZardSkeletonComponent],
  template: `
    <div class="p-4 h-full flex flex-col">
      <div class="flex items-start justify-between shrink-0 mb-4">
        <div>
          <h2 class="text-lg font-semibold">Help</h2>
        </div>
        <div>
          <button type="button" z-button zType="ghost" zSize="sm" (click)="help.close()">
            <z-icon zType="x"></z-icon>
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto pr-2 hide-scrollbar">
        <!-- Loading State -->
        <div *ngIf="help.isLoading()" class="space-y-4 animate-pulse">
          <z-skeleton class="h-8 w-3/4 mb-4"></z-skeleton>
          <z-skeleton class="h-4 w-full"></z-skeleton>
          <z-skeleton class="h-4 w-full"></z-skeleton>
          <z-skeleton class="h-4 w-5/6"></z-skeleton>
          <div class="mt-6">
            <z-skeleton class="h-6 w-1/2 mb-2"></z-skeleton>
            <z-skeleton class="h-4 w-full"></z-skeleton>
            <z-skeleton class="h-4 w-full"></z-skeleton>
          </div>
        </div>

        <!-- Markdown Content -->
        <div
          *ngIf="contentHtml(); else fallback"
          [innerHTML]="contentHtml()"
          class="markdown-content text-sm text-slate-700 space-y-3"
        ></div>

        <!-- Fallback (Old Behavior) -->
        <ng-template #fallback>
          <div *ngIf="!help.isLoading()" class="space-y-4">
            <div *ngIf="context()?.briefExplanation">
              <h3 class="text-sm font-medium text-slate-700">Brief Explanation</h3>
              <p class="text-sm text-slate-600 mt-1">{{ context()?.briefExplanation }}</p>
            </div>

            <div *ngIf="context()?.details">
              <h3 class="text-sm font-medium text-slate-700">Details</h3>
              <p class="text-sm text-slate-600 mt-1">{{ context()?.details }}</p>
            </div>

            <div *ngIf="!context()?.briefExplanation && !context()?.details">
              <p class="text-sm text-slate-600">
                More detailed help will appear here for the current view.
              </p>
            </div>
          </div>
        </ng-template>
      </div>
    </div>
  `,
  styles: [
    `
      .hide-scrollbar {
        -ms-overflow-style: none; /* IE and Edge */
        scrollbar-width: none; /* Firefox */
      }
      .hide-scrollbar::-webkit-scrollbar {
        display: none; /* Chrome, Safari and Opera */
      }
      .markdown-content h1 {
        font-size: 1.5rem;
        font-weight: 700;
        margin-bottom: 1rem;
        color: var(--foreground);
      }
      .markdown-content h2 {
        font-size: 1.25rem;
        font-weight: 600;
        margin-top: 1.5rem;
        margin-bottom: 0.75rem;
        color: var(--foreground);
      }
      .markdown-content h3 {
        font-size: 1.1rem;
        font-weight: 600;
        margin-top: 1.25rem;
        margin-bottom: 0.5rem;
        color: var(--foreground);
      }
      .markdown-content p {
        margin-bottom: 0.75rem;
        line-height: 1.6;
      }
      .markdown-content ul {
        list-style-type: disc;
        padding-left: 1.5rem;
        margin-bottom: 1rem;
      }
      .markdown-content li {
        margin-bottom: 0.25rem;
      }
      .markdown-content strong {
        font-weight: 600;
        color: var(--foreground);
      }
    `,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
  host: {
    class: 'block h-full',
  },
})
export class HelpDrawerContentComponent {
  readonly help = inject(HelpService);
  private readonly sanitizer = inject(DomSanitizer);
  readonly context = this.help.context;

  readonly contentHtml = computed(() => {
    const rawContent = this.help.helpContent();
    if (!rawContent) return null;
    const html = marked.parse(rawContent, { async: false }) as string;
    return this.sanitizer.bypassSecurityTrustHtml(html);
  });
}
