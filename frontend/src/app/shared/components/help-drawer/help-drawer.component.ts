import { ZardSheetRef } from '@/shared/components/sheet/sheet-ref';
import { ZardSheetService } from '@/shared/components/sheet/sheet.service';
import { HelpService } from '@/shared/services/help.service';
import { ChangeDetectionStrategy, Component, effect, inject, OnDestroy } from '@angular/core';
import { HelpDrawerContentComponent } from './help-drawer-content.component';

@Component({
  selector: 'z-help-drawer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '',
})
export class HelpDrawerComponent implements OnDestroy {
  private readonly help = inject(HelpService);
  private readonly sheet = inject(ZardSheetService);

  private sheetRef: ZardSheetRef | null = null;

  // react to visible signal
  private readonly visible = this.help.visible;

  constructor() {
    // Open/close sheet based on the signal. Use `effect` so the subscription remains active
    // for the life of the component (computed can be GC'd if not referenced).
    effect(() => {
      const v = this.visible();
      if (v && !this.sheetRef) {
        this.openSheet();
      } else if (!v && this.sheetRef) {
        this.sheetRef.close();
        this.sheetRef = null;
      }
    });
  }

  private openSheet() {
    // Use service to open sheet with our content component
    this.sheetRef = this.sheet.create({
      zContent: HelpDrawerContentComponent,
      // Header and close button are rendered by HelpDrawerContentComponent
      zClosable: false,
      zSide: 'right',
      zSize: 'default',
      zWidth: '420px',
      zData: null,
      zMaskClosable: true,
      zHideFooter: true,
    });

    // Ensure closing the signal when sheet is closed externally
    // There's no close event; we rely on HelpService to keep state, so when sheetRef closes, set help.close()
    // Patch the close method to also set the help service state when closed
    const originalClose = this.sheetRef.close.bind(this.sheetRef);
    this.sheetRef.close = (result?: any) => {
      originalClose(result);
      this.help.close();
      this.sheetRef = null;
    };
  }

  ngOnDestroy(): void {
    if (this.sheetRef) {
      this.sheetRef.close();
      this.sheetRef = null;
    }
  }
}
