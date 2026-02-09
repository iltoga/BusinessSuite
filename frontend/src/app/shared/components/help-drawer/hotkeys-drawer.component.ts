import { ZardSheetRef } from '@/shared/components/sheet/sheet-ref';
import { ZardSheetService } from '@/shared/components/sheet/sheet.service';
import { HelpService } from '@/shared/services/help.service';
import { ChangeDetectionStrategy, Component, effect, inject, OnDestroy } from '@angular/core';
import { HotkeysDrawerContentComponent } from './hotkeys-drawer-content.component';

@Component({
  selector: 'z-hotkeys-drawer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '',
})
export class HotkeysDrawerComponent implements OnDestroy {
  private readonly help = inject(HelpService);
  private readonly sheet = inject(ZardSheetService);

  private sheetRef: ZardSheetRef | null = null;

  // react to cheatsheetVisible signal
  private readonly visible = this.help.cheatsheetVisible;

  constructor() {
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
    this.sheetRef = this.sheet.create({
      zContent: HotkeysDrawerContentComponent,
      zTitle: 'Keyboard Shortcuts',
      zDescription: '',
      zSide: 'right',
      zSize: 'default',
      zWidth: '560px',
      zData: null,
      zMaskClosable: true,
      zHideFooter: true,
    });

    const originalClose = this.sheetRef.close.bind(this.sheetRef);
    this.sheetRef.close = (result?: any) => {
      originalClose(result);
      this.help.closeCheatsheet();
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
