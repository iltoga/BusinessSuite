import { Overlay } from '@angular/cdk/overlay';
import { ComponentPortal } from '@angular/cdk/portal';
import {
  Injectable,
  Injector,
  inject,
  inputBinding,
  outputBinding,
  type Type,
} from '@angular/core';

import { ImageViewerHostComponent } from '@/shared/components/image-viewer-host/image-viewer-host.component';
import { PdfViewerHostComponent } from '@/shared/components/pdf-viewer-host/pdf-viewer-host.component';

type ViewerComponent = ImageViewerHostComponent | PdfViewerHostComponent;

type MaskClosableDialogRef = {
  setMaskClosable(maskClosable: boolean): void;
  isMaskClosable?: () => boolean;
};

@Injectable({ providedIn: 'root' })
export class DocumentViewerOverlayService {
  private readonly overlay = inject(Overlay);
  private readonly injector = inject(Injector);

  private currentRef: {
    overlayRef: any;
    componentRef: any;
    removeEscapeListener?: () => void;
    restoreDialogMaskClosable?: () => void;
  } | null = null;

  openImageViewer(
    src: Blob | string,
    options?: {
      dialogRef?: MaskClosableDialogRef;
      downloadFileName?: string;
      showDownloadButton?: boolean;
    },
  ): void {
    this.openViewer(ImageViewerHostComponent, src, options);
  }

  openPdfViewer(
    src: Blob | string,
    options?: {
      dialogRef?: MaskClosableDialogRef;
      downloadFileName?: string;
      showDownloadButton?: boolean;
    },
  ): void {
    this.openViewer(PdfViewerHostComponent, src, options);
  }

  closeCurrent(): void {
    const current = this.currentRef;
    if (!current) {
      return;
    }

    this.currentRef = null;

    try {
      current.removeEscapeListener?.();
    } catch {
      // ignore
    }

    try {
      current.restoreDialogMaskClosable?.();
    } catch {
      // ignore
    }

    try {
      current.componentRef.destroy();
    } catch {
      // ignore
    }

    try {
      current.overlayRef.dispose();
    } catch {
      // ignore
    }
  }

  private openViewer<T extends ViewerComponent>(
    componentType: Type<T>,
    src: Blob | string,
    options?: {
      dialogRef?: MaskClosableDialogRef;
      downloadFileName?: string;
      showDownloadButton?: boolean;
    },
  ): void {
    this.closeCurrent();

    const overlayRef = this.overlay.create({
      hasBackdrop: true,
      backdropClass: 'cdk-overlay-dark-backdrop',
      positionStrategy: this.overlay.position().global().top('0').left('0'),
      scrollStrategy: this.overlay.scrollStrategies.block(),
    });

    const overlayHostElement = overlayRef.overlayElement.parentElement as HTMLElement | null;
    if (overlayHostElement) {
      overlayHostElement.style.zIndex = '2147483647';
    }
    overlayRef.hostElement.style.zIndex = '2147483647';
    overlayRef.overlayElement.style.zIndex = '2147483647';

    const bindings = [
      inputBinding('src', () => src),
      inputBinding('appendToBody', () => false),
      ...(options?.downloadFileName !== undefined
        ? [inputBinding('downloadFileName', () => options.downloadFileName)]
        : []),
      ...(options?.showDownloadButton !== undefined
        ? [inputBinding('showDownloadButton', () => options.showDownloadButton)]
        : []),
      outputBinding('closed', () => this.closeCurrent()),
    ];

    const componentRef = overlayRef.attach(
      new ComponentPortal(componentType, undefined, this.injector, undefined, bindings),
    );

    const previousMaskClosable = options?.dialogRef?.isMaskClosable?.();
    if (options?.dialogRef) {
      options.dialogRef.setMaskClosable(false);
    }

    const escapeHandler = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') {
        return;
      }

      event.preventDefault();
      if (typeof event.stopImmediatePropagation === 'function') {
        event.stopImmediatePropagation();
      } else {
        event.stopPropagation();
      }
      this.closeCurrent();
    };

    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', escapeHandler, true);
    }

    overlayRef.backdropClick().subscribe(() => {
      componentRef.instance.close?.();
    });

    this.currentRef = {
      overlayRef,
      componentRef,
      restoreDialogMaskClosable:
        options?.dialogRef && previousMaskClosable !== undefined
          ? () => options.dialogRef?.setMaskClosable(previousMaskClosable)
          : options?.dialogRef
            ? () => options.dialogRef?.setMaskClosable(true)
            : undefined,
      removeEscapeListener: () => {
        if (typeof window !== 'undefined') {
          window.removeEventListener('keydown', escapeHandler, true);
        }
      },
    };
  }
}
