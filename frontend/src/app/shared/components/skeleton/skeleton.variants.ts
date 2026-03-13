import { cva, type VariantProps } from 'class-variance-authority';

export const skeletonVariants = cva('bg-accent skeleton-delay rounded-md');
export type ZardSkeletonVariants = VariantProps<typeof skeletonVariants>;
