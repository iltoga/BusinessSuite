import { vi } from 'vitest';

import { ZardComboboxComponent } from './combobox.component';

describe('ZardComboboxComponent', () => {
  it('does not clear the current selection when the same option is reselected in non-toggle mode', () => {
    const component = Object.create(ZardComboboxComponent.prototype) as any;
    const hide = vi.fn();
    const focus = vi.fn();

    component.getCurrentValue = () => '21';
    component.toggleOnReselect = () => false;
    component.internalValue = { set: vi.fn() };
    component.onChange = vi.fn();
    component.zValueChange = { emit: vi.fn() };
    component.zComboSelected = { emit: vi.fn() };
    component.popoverDirective = () => ({ hide });
    component.buttonRef = () => ({ nativeElement: { focus } });
    component.groups = () => [];
    component.options = () => [];

    component.handleSelect({ value: '21', label: 'Selected option' });

    expect(component.internalValue.set).not.toHaveBeenCalled();
    expect(component.onChange).not.toHaveBeenCalled();
    expect(component.zValueChange.emit).not.toHaveBeenCalled();
    expect(component.zComboSelected.emit).not.toHaveBeenCalled();
    expect(hide).toHaveBeenCalledTimes(1);
    expect(focus).toHaveBeenCalledTimes(1);
  });
});
