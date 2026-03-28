import { ElementRef, PLATFORM_ID, RendererFactory2 } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Overlay, OverlayPositionBuilder } from '@angular/cdk/overlay';
import { Subject } from 'rxjs';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { ZardDropdownService } from './dropdown.service';

describe('ZardDropdownService', () => {
  let service: ZardDropdownService;
  let outsideEvents$: Subject<any>;
  let overlayRefMock: {
    overlayElement: HTMLElement;
    attach: ReturnType<typeof vi.fn>;
    detach: ReturnType<typeof vi.fn>;
    dispose: ReturnType<typeof vi.fn>;
    hasAttached: ReturnType<typeof vi.fn>;
    updatePosition: ReturnType<typeof vi.fn>;
    outsidePointerEvents: ReturnType<typeof vi.fn>;
  };
  let rendererListenSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      cb(0);
      return 0;
    });

    outsideEvents$ = new Subject();
    const overlayElement = document.createElement('div');
    const menu = document.createElement('div');
    menu.setAttribute('role', 'menu');
    const itemOne = document.createElement('button');
    itemOne.setAttribute('z-dropdown-menu-item', '');
    const itemTwo = document.createElement('button');
    itemTwo.setAttribute('z-dropdown-menu-item', '');
    itemTwo.dataset['disabled'] = 'true';
    const itemThree = document.createElement('button');
    itemThree.setAttribute('z-dropdown-menu-item', '');
    overlayElement.append(menu, itemOne, itemTwo, itemThree);

    overlayRefMock = {
      overlayElement,
      attach: vi.fn(),
      detach: vi.fn(),
      dispose: vi.fn(),
      hasAttached: vi.fn(() => true),
      updatePosition: vi.fn(),
      outsidePointerEvents: vi.fn(() => outsideEvents$.asObservable()),
    };
    rendererListenSpy = vi.fn(() => vi.fn());

    TestBed.configureTestingModule({
      providers: [
        ZardDropdownService,
        { provide: PLATFORM_ID, useValue: 'browser' },
        {
          provide: RendererFactory2,
          useValue: { createRenderer: vi.fn(() => ({ listen: rendererListenSpy })) },
        },
        {
          provide: Overlay,
          useValue: {
            create: vi.fn(() => overlayRefMock),
            position: vi.fn(() => ({
              flexibleConnectedTo: vi.fn(() => ({
                withPositions: vi.fn().mockReturnThis(),
                withPush: vi.fn().mockReturnThis(),
              })),
            })),
            scrollStrategies: { reposition: vi.fn(() => ({ kind: 'reposition' })) },
          },
        },
        {
          provide: OverlayPositionBuilder,
          useValue: {
            flexibleConnectedTo: vi.fn(() => ({
              withPositions: vi.fn().mockReturnThis(),
              withPush: vi.fn().mockReturnThis(),
            })),
          },
        },
      ],
    });

    service = TestBed.inject(ZardDropdownService);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
    TestBed.resetTestingModule();
  });

  it('opens the dropdown, exposes items, and closes on outside clicks', () => {
    const trigger = new ElementRef(document.createElement('button'));
    const template = {} as never;
    const viewContainerRef = {} as never;

    service.toggle(trigger, template, viewContainerRef);
    vi.runAllTimers();

    expect(service.isOpen()).toBe(true);
    expect(overlayRefMock.attach).toHaveBeenCalled();
    expect(service.getDropdownItems()).toHaveLength(2);

    const firstItem = service.getDropdownItems()[0];
    const focusSpy = vi.spyOn(firstItem, 'focus');
    service.setFocusedIndex(0);
    expect(focusSpy).toHaveBeenCalled();
    expect(service.focusedIndex()).toBe(0);

    outsideEvents$.next({ target: document.createElement('div') });
    expect(service.isOpen()).toBe(false);
    expect(overlayRefMock.detach).toHaveBeenCalled();
    expect(overlayRefMock.dispose).toHaveBeenCalled();
  });
});
