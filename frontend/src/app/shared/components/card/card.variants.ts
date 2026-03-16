import { cva } from 'class-variance-authority';

import { mergeClasses } from '@/shared/utils/merge-classes';

export const cardVariants = cva(
  'bg-card text-card-foreground flex flex-col rounded-xl border shadow-sm',
  {
    variants: {
      variant: {
        /** Default spacious layout — 24px top/bottom padding, 24px column gap */
        default: 'gap-6 py-6',
        /** Compact layout — 16px top/bottom padding, 16px column gap */
        compact: 'gap-4 py-4',
        /** Flat layout — no host padding or gap; use for table-style cards */
        flat: 'gap-0 py-0',
      },
    },
    defaultVariants: { variant: 'default' },
  },
);

export const cardHeaderVariants = cva(
  mergeClasses(
    '@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start gap-2',
    'has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6',
  ),
  {
    variants: {
      variant: {
        default: 'px-6',
        compact: 'px-4',
        flat: 'px-0',
      },
    },
    defaultVariants: { variant: 'default' },
  },
);

export const cardActionVariants = cva(
  'col-start-2 row-span-2 row-start-1 self-start justify-self-end',
);

export const cardBodyVariants = cva('', {
  variants: {
    variant: {
      default: 'px-6',
      compact: 'px-4',
      flat: 'px-0',
    },
  },
  defaultVariants: { variant: 'default' },
});

export const cardFooterVariants = cva('flex flex-col gap-2 items-center', {
  variants: {
    variant: {
      default: 'px-6 [.border-t]:pt-6',
      compact: 'px-4 [.border-t]:pt-4',
      flat: 'px-0',
    },
  },
  defaultVariants: { variant: 'default' },
});
