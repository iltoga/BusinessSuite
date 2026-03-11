import { cva, type VariantProps } from 'class-variance-authority';

import { mergeClasses } from '@/shared/utils/merge-classes';

export const switchVariants = cva(
  mergeClasses(
    'peer inline-flex shrink-0 cursor-pointer items-center rounded-full border border-transparent transition-colors',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    'disabled:cursor-not-allowed disabled:opacity-50 data-[state=unchecked]:bg-input',
  ),
  {
    variants: {
      zSize: {
        default: 'h-6 w-11',
        sm: 'h-5 w-9',
        lg: 'h-7 w-12',
      },
      zType: {
        default: 'data-[state=checked]:bg-primary',
        destructive: 'data-[state=checked]:bg-destructive',
      },
    },
    defaultVariants: {
      zSize: 'default',
      zType: 'default',
    },
  },
);

export type ZardSwitchSizeVariants = NonNullable<VariantProps<typeof switchVariants>['zSize']>;
export type ZardSwitchTypeVariants = NonNullable<VariantProps<typeof switchVariants>['zType']>;
