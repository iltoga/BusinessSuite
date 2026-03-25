/**
 * Regression tests for subscription cleanup patterns.
 *
 * These tests verify that long-lived observable subscriptions (valueChanges,
 * router events, Subjects) are properly terminated via takeUntilDestroyed
 * or equivalent cleanup mechanisms, preventing memory leaks.
 */
import { DestroyRef, EnvironmentInjector, runInInjectionContext } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TestBed } from '@angular/core/testing';
import { FormBuilder, FormControl, FormGroup } from '@angular/forms';
import { Subject } from 'rxjs';
import { describe, expect, it } from 'vitest';

describe('Subscription cleanup via takeUntilDestroyed', () => {
  it('takeUntilDestroyed completes the subscription when DestroyRef fires', () => {
    const teardownCallbacks: Array<() => void> = [];
    const mockDestroyRef: DestroyRef = {
      onDestroy(cb: () => void) {
        teardownCallbacks.push(cb);
        return () => undefined;
      },
    } as DestroyRef;

    const control = new FormControl('initial');
    const values: string[] = [];

    control.valueChanges
      .pipe(takeUntilDestroyed(mockDestroyRef))
      .subscribe((v) => values.push(v as string));

    control.setValue('a');
    expect(values).toEqual(['a']);

    // Simulate component destruction
    teardownCallbacks.forEach((cb) => cb());

    control.setValue('b');
    expect(values).toEqual(['a']); // 'b' must NOT arrive
  });

  it('multiple valueChanges on the same DestroyRef all stop together', () => {
    const teardownCallbacks: Array<() => void> = [];
    const mockDestroyRef: DestroyRef = {
      onDestroy(cb: () => void) {
        teardownCallbacks.push(cb);
        return () => undefined;
      },
    } as DestroyRef;

    const fb = new FormBuilder();
    const form = fb.group({
      fieldA: [''],
      fieldB: [''],
    });

    const aValues: string[] = [];
    const bValues: string[] = [];

    form
      .get('fieldA')!
      .valueChanges.pipe(takeUntilDestroyed(mockDestroyRef))
      .subscribe((v) => aValues.push(v as string));

    form
      .get('fieldB')!
      .valueChanges.pipe(takeUntilDestroyed(mockDestroyRef))
      .subscribe((v) => bValues.push(v as string));

    form.patchValue({ fieldA: 'x', fieldB: 'y' });
    expect(aValues).toEqual(['x']);
    expect(bValues).toEqual(['y']);

    teardownCallbacks.forEach((cb) => cb());

    form.patchValue({ fieldA: 'x2', fieldB: 'y2' });
    expect(aValues).toEqual(['x']);
    expect(bValues).toEqual(['y']);
  });

  it('Subject subscription stops receiving after DestroyRef fires', () => {
    const teardownCallbacks: Array<() => void> = [];
    const mockDestroyRef: DestroyRef = {
      onDestroy(cb: () => void) {
        teardownCallbacks.push(cb);
        return () => undefined;
      },
    } as DestroyRef;

    const subject$ = new Subject<number>();
    const received: number[] = [];

    subject$.pipe(takeUntilDestroyed(mockDestroyRef)).subscribe((v) => received.push(v));

    subject$.next(1);
    subject$.next(2);
    expect(received).toEqual([1, 2]);

    teardownCallbacks.forEach((cb) => cb());

    subject$.next(3);
    expect(received).toEqual([1, 2]);
  });

  it('form control enable/disable sync pattern stops after destroy', () => {
    // Mirrors the product-form syncTaskNotifyCustomerAvailability pattern
    const teardownCallbacks: Array<() => void> = [];
    const mockDestroyRef: DestroyRef = {
      onDestroy(cb: () => void) {
        teardownCallbacks.push(cb);
        return () => undefined;
      },
    } as DestroyRef;

    const group = new FormGroup({
      addTaskToCalendar: new FormControl(false),
      notifyCustomer: new FormControl(false),
    });

    const notifyControl = group.get('notifyCustomer')!;
    const calendarControl = group.get('addTaskToCalendar')!;

    const applyState = (enabled: boolean) => {
      if (enabled) {
        notifyControl.enable({ emitEvent: false });
      } else {
        notifyControl.setValue(false, { emitEvent: false });
        notifyControl.disable({ emitEvent: false });
      }
    };

    applyState(Boolean(calendarControl.value));
    calendarControl.valueChanges
      .pipe(takeUntilDestroyed(mockDestroyRef))
      .subscribe((enabled) => applyState(Boolean(enabled)));

    // Before destroy: toggling calendar enables notify
    calendarControl.setValue(true);
    expect(notifyControl.enabled).toBe(true);

    calendarControl.setValue(false);
    expect(notifyControl.disabled).toBe(true);

    // After destroy: changes should NOT propagate
    teardownCallbacks.forEach((cb) => cb());

    calendarControl.setValue(true);
    // notify stays disabled because subscription was cleaned up
    expect(notifyControl.disabled).toBe(true);
  });

  it('TestBed DestroyRef unsubscribes on environment teardown', () => {
    TestBed.configureTestingModule({});

    const injector = TestBed.inject(EnvironmentInjector);
    let received = 0;
    const control = new FormControl(0);

    runInInjectionContext(injector, () => {
      control.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => received++);
    });

    control.setValue(1);
    expect(received).toBe(1);

    // Tearing down TestBed destroys the injector
    TestBed.resetTestingModule();

    control.setValue(2);
    expect(received).toBe(1);
  });
});
