import { ZardIcon } from '@/shared/components/icon/icons';

export type MenuVisibilityCondition = boolean | (() => boolean);

export interface MenuItemAccessibility {
  ariaLabel?: string;
  ariaControls?: string;
  ariaHasPopup?: 'menu' | 'true' | 'false';
}

export interface MenuItem {
  id: string;
  label: string;
  icon?: ZardIcon;
  route?: string;
  action?: () => void;
  children?: MenuItem[];
  collapsible?: boolean;
  visible?: MenuVisibilityCondition;
  disabled?: MenuVisibilityCondition;
  accessibility?: MenuItemAccessibility;
}
