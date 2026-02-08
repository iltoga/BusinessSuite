import { cva, type VariantProps } from 'class-variance-authority';

export const dropdownContentVariants = cva(
  'bg-popover text-popover-foreground z-50 min-w-50 overflow-y-auto rounded-md border py-1 px-1 shadow-md',
);

export const dropdownItemVariants = cva(
  'relative flex cursor-pointer select-none items-center gap-3 rounded-md px-3 py-2 text-sm outline-none transition-colors hover:bg-accent/50 hover:text-foreground focus:bg-accent/50 focus:text-foreground data-[highlighted]:bg-accent/50 data-[highlighted]:text-foreground data-[highlighted=true]:bg-accent/50 data-[highlighted=true]:text-foreground data-disabled:pointer-events-none data-disabled:opacity-50 data-disabled:cursor-not-allowed [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: '',
        destructive: '[&_svg]:text-destructive',
        warning: '[&_svg]:text-warning',
        success: '[&_svg]:text-success',
        secondary: '[&_svg]:text-secondary',
        outline: '',
        ghost: '',
      },
      inset: {
        true: 'pl-8',
        false: '',
      },
    },
    defaultVariants: {
      variant: 'default',
      inset: false,
    },
  },
);

export type ZardDropdownItemVariants = VariantProps<typeof dropdownItemVariants>;
