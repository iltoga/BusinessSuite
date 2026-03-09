/**
 * Data for delete dialog
 */
export interface DeleteDialogData {
  /** Entity label (e.g., 'Customer', 'Product') */
  entityLabel: string;
  /** Total count of items to delete */
  totalCount?: number;
  /** Delete all or selected */
  mode?: 'all' | 'selected';
  /** Details text to show */
  detailsText?: string;
  /** Extra checkbox label (optional) */
  extraCheckboxLabel?: string | null;
  /** Extra checkbox tooltip */
  extraCheckboxTooltip?: string | null;
}

/**
 * Result from delete dialog confirmation
 */
export interface DeleteDialogResult {
  /** Whether extra checkbox was checked */
  extraChecked?: boolean;
}
