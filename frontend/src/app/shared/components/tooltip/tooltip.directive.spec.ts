import { Overlay, OverlayPositionBuilder } from '@angular/cdk/overlay';
import { DOCUMENT } from '@angular/common';
import { Component, PLATFORM_ID, Renderer2 } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ZardTooltipDirective } from './tooltip';

@Component({
  standalone: true,
  imports: [ZardTooltipDirective],
  template: `<button zTooltip>Hover</button>`,
})
class TooltipHostComponent {}

describe('ZardTooltipDirective', () => {
  let overlayRefMock: {
    outsidePointerEvents: ReturnType<typeof vi.fn>;
    create: ReturnType<typeof vi.fn>;
    dispose: ReturnType<typeof vi.fn>;
  };
  let rendererListenSpy: ReturnType<typeof vi.fn>;
  let destroyCallback: (() => void) | undefined;

  beforeEach(() => {
    TestBed.resetTestingModule();
    const outsideEvents$ = new Subject<any>();
    overlayRefMock = {
      outsidePointerEvents: vi.fn(() => outsideEvents$.asObservable()),
      create: vi.fn(),
      dispose: vi.fn(),
    } as any;
    rendererListenSpy = vi.fn(() => vi.fn());

    TestBed.configureTestingModule({
      imports: [TooltipHostComponent],
      providers: [
        { provide: PLATFORM_ID, useValue: 'browser' },
        {
          provide: Overlay,
          useValue: {
            create: vi.fn(() => overlayRefMock),
            position: vi.fn(() => ({
              flexibleConnectedTo: vi.fn(() => ({
                withPositions: vi.fn().mockReturnThis(),
              })),
            })),
          },
        },
        {
          provide: OverlayPositionBuilder,
          useValue: {
            flexibleConnectedTo: vi.fn(() => ({
              withPositions: vi.fn().mockReturnThis(),
            })),
          },
        },
        { provide: DOCUMENT, useValue: document },
        { provide: Renderer2, useValue: { listen: rendererListenSpy } },
      ],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });

  it('initializes overlay listeners and disposes the overlay on destroy', () => {
    const fixture = TestBed.createComponent(TooltipHostComponent);
    fixture.detectChanges();

    expect(TestBed.inject(Overlay).create).toHaveBeenCalled();

    fixture.destroy();

    expect(overlayRefMock.dispose).toHaveBeenCalled();
  });
});
