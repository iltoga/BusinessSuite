import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Overlay } from '@angular/cdk/overlay';
import { EventEmitter } from '@angular/core';
import { Subject } from 'rxjs';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { ZardDialogOptions } from './dialog.component';
import { ZardDialogService } from './dialog.service';

class TestDialogContentComponent {}

describe('ZardDialogService', () => {
  let service: ZardDialogService;
  let overlayRefMock: any;
  let overlayMock: any;

  beforeEach(() => {
    overlayRefMock = {
      attach: vi.fn(),
    };
    overlayMock = {
      position: vi.fn(() => ({
        global: vi.fn(() => ({ strategy: 'global-position' })),
      })),
      create: vi.fn(() => overlayRefMock),
    };

    TestBed.configureTestingModule({
      providers: [
        ZardDialogService,
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: Overlay, useValue: overlayMock },
      ],
    });

    service = TestBed.inject(ZardDialogService);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });

  it('creates a dialog overlay and attaches component content', () => {
    const dialogContainer = {
      cancelTriggered: new EventEmitter<void>(),
      okTriggered: new EventEmitter<void>(),
      getNativeElement: vi.fn(() => document.createElement('div')),
      attachComponentPortal: vi.fn(() => ({ instance: { confirmed: true } })),
      attachTemplatePortal: vi.fn(),
      dialogRef: undefined,
    };
    overlayRefMock.attach = vi.fn(() => ({ instance: dialogContainer }));
    overlayRefMock.outsidePointerEvents = vi.fn(() => new Subject<void>().asObservable()) as any;

    const dialogRef = service.create({
      zContent: TestDialogContentComponent as never,
      zData: { documentId: 42 },
    } as ZardDialogOptions<TestDialogContentComponent, { documentId: number }>);

    expect(overlayMock.create).toHaveBeenCalled();
    expect(overlayRefMock.attach).toHaveBeenCalled();
    expect(dialogContainer.attachComponentPortal).toHaveBeenCalled();
    expect(dialogContainer.dialogRef).toBe(dialogRef);
    expect(dialogRef.componentInstance).toEqual({ confirmed: true });
  });
});
