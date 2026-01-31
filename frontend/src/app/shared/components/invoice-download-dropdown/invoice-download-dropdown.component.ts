import { InvoicesService } from '@/core/api/api/invoices.service';
import { ZardButtonComponent } from '@/shared/components/button/button.component';
import {
  ZardButtonSizeVariants,
  ZardButtonTypeVariants,
} from '@/shared/components/button/button.variants';
import { ZardDropdownImports } from '@/shared/components/dropdown/dropdown.imports';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import { downloadBlob } from '@/shared/utils/file-download';
import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';

@Component({
  selector: 'app-invoice-download-dropdown',
  standalone: true,
  imports: [CommonModule, ...ZardDropdownImports, ZardButtonComponent, ZardIconComponent],
  templateUrl: './invoice-download-dropdown.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceDownloadDropdownComponent {
  private invoicesService = inject(InvoicesService);

  invoiceId = input.required<number>();
  invoiceNumber = input.required<string>();
  customerName = input.required<string>();
  zType = input<ZardButtonTypeVariants>('secondary');
  zSize = input<ZardButtonSizeVariants>('sm');

  loading = signal(false);

  download(format: 'docx' | 'pdf') {
    if (this.loading()) return;

    this.loading.set(true);
    this.invoicesService.invoicesDownloadRetrieve(this.invoiceId(), format).subscribe({
      next: (blob: Blob) => {
        const extension = format === 'pdf' ? 'pdf' : 'docx';
        const filename = `${this.invoiceNumber()}_${this.customerName()}.${extension}`.replace(
          /\s+/g,
          '_',
        );
        downloadBlob(blob, filename);
        this.loading.set(false);
      },
      error: (err: any) => {
        console.error('Download failed', err);
        this.loading.set(false);
      },
    });
  }
}
