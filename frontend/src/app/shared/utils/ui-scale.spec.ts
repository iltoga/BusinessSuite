import { vi } from 'vitest';

import {
  isWindowsPlatform,
  readCurrentUiScaleFactor,
  readOverlayTriggerWidthPx,
  scaleOverlayMaxHeightPx,
} from './ui-scale';

describe('ui-scale utilities', () => {
  afterEach(() => {
    document.documentElement.style.removeProperty('--app-ui-scale');
    document.documentElement.style.removeProperty('zoom');
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('detects Windows platforms', () => {
    expect(isWindowsPlatform({ platform: 'Win32' } as Navigator)).toBe(true);
    expect(isWindowsPlatform({ platform: 'MacIntel' } as Navigator)).toBe(false);
  });

  it('reads the current UI scale from the root css variable', () => {
    document.documentElement.style.setProperty('--app-ui-scale', '0.8');

    expect(readCurrentUiScaleFactor(document)).toBeCloseTo(0.8, 6);
  });

  it('keeps the visual trigger width on non-Windows platforms', () => {
    const trigger = document.createElement('button');
    document.body.appendChild(trigger);

    Object.defineProperty(trigger, 'offsetWidth', {
      configurable: true,
      get: () => 200,
    });
    vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({
      width: 150,
      height: 40,
      top: 0,
      right: 150,
      bottom: 40,
      left: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);

    expect(readOverlayTriggerWidthPx(trigger, { platform: 'MacIntel' } as Navigator)).toBe(150);
  });

  it('uses the unscaled trigger width for Windows overlays when UI zoom is reduced', () => {
    document.documentElement.style.setProperty('--app-ui-scale', '0.75');

    const trigger = document.createElement('button');
    document.body.appendChild(trigger);

    Object.defineProperty(trigger, 'offsetWidth', {
      configurable: true,
      get: () => 200,
    });
    vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({
      width: 150,
      height: 40,
      top: 0,
      right: 150,
      bottom: 40,
      left: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);

    expect(readOverlayTriggerWidthPx(trigger, { platform: 'Win32' } as Navigator)).toBe(200);
  });

  it('expands overlay max height to preserve visual space on Windows with UI zoom', () => {
    document.documentElement.style.setProperty('--app-ui-scale', '0.75');

    expect(scaleOverlayMaxHeightPx(384, document, { platform: 'Win32' } as Navigator)).toBe(
      Math.round(384 / 0.75),
    );
    expect(scaleOverlayMaxHeightPx(384, document, { platform: 'MacIntel' } as Navigator)).toBe(384);
  });
});
