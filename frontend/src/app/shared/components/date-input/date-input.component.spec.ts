import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { ConfigService } from '@/core/services/config.service';
import { ZardDateInputComponent } from './date-input.component';

describe('ZardDateInputComponent', () => {
  let component: ZardDateInputComponent;
  const configServiceMock = {
    config: signal({ dateFormat: 'dd-MM-yyyy' }),
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [{ provide: ConfigService, useValue: configServiceMock }],
    });

    component = TestBed.runInInjectionContext(() => new ZardDateInputComponent());
  });

  afterEach(() => {
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });

  it('formats written values using the configured date format', () => {
    component.writeValue(new Date(2026, 2, 20));

    expect(component.value()).toEqual(new Date(2026, 2, 20));
    expect((component as any).displayValue()).toBe('20-03-2026');
  });

  it('parses the configured format on blur and emits the converted date', () => {
    const onChange = vi.fn();
    const onTouched = vi.fn();
    component.registerOnChange(onChange);
    component.registerOnTouched(onTouched);

    (component as any).onInput({ target: { value: '20-03-2026' } } as unknown as Event);
    (component as any).onBlur();

    expect(component.value()).toEqual(new Date(2026, 2, 20));
    expect(onChange).toHaveBeenCalledWith(new Date(2026, 2, 20));
    expect(onTouched).toHaveBeenCalled();
  });

  it('falls back to alternate formats and clears when the input is blank', () => {
    const onChange = vi.fn();
    const onTouched = vi.fn();
    component.registerOnChange(onChange);
    component.registerOnTouched(onTouched);

    (component as any).onInput({ target: { value: '2026-03-20' } } as unknown as Event);
    (component as any).onBlur();

    expect(component.value()).toEqual(new Date(2026, 2, 20));
    expect(onChange).toHaveBeenCalledWith(new Date(2026, 2, 20));

    (component as any).onInput({ target: { value: '' } } as unknown as Event);
    (component as any).onBlur();

    expect(component.value()).toBeNull();
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(onTouched).toHaveBeenCalledTimes(2);
  });

  it('uses the first calendar date and hides the popover when a selection is made', () => {
    const hide = vi.fn();
    Object.defineProperty(component as any, 'popoverDirective', {
      value: () => ({ hide }),
    });
    const onChange = vi.fn();
    const onTouched = vi.fn();
    component.registerOnChange(onChange);
    component.registerOnTouched(onTouched);

    (component as any).onCalendarDateChange([new Date(2026, 3, 1), new Date(2026, 3, 2)]);

    expect(component.value()).toEqual(new Date(2026, 3, 1));
    expect((component as any).displayValue()).toBe('01-04-2026');
    expect(onChange).toHaveBeenCalledWith(new Date(2026, 3, 1));
    expect(onTouched).toHaveBeenCalled();
    expect(hide).toHaveBeenCalled();
  });

  it('renders a trimmed custom placeholder and supports disabling', () => {
    Object.assign(component as any, {
      placeholder: () => '  Choose a day  ',
    });

    expect((component as any).effectivePlaceholder()).toBe('Choose a day');

    component.setDisabledState(true);
    expect(component.disabled()).toBe(true);
  });
});
