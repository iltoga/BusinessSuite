import type { DocApplicationInvoice, Product } from '@/core/api';

// ── Interfaces ─────────────────────────────────────────────────────────

export interface BillableProductRow {
  product: Product;
  pendingApplications: DocApplicationInvoice[];
  pendingApplicationsCount: number;
  hasPendingApplications: boolean;
}

export interface InvoiceLineInitial {
  id?: number;
  product?: number | null;
  customerApplication?: number | null;
  amount?: number;
  locked?: boolean;
}

// ── Type Coercion ──────────────────────────────────────────────────────

export function parseComboboxNumericValue(value: string | null): number | null {
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function resolveProductPriceFromProduct(product: Product | null | undefined): number {
  if (!product) {
    return 0;
  }
  const retail = (product as any).retailPrice;
  const base = (product as any).basePrice;
  const price = Number(retail ?? base ?? 0);
  return Number.isNaN(price) ? 0 : price;
}

// ── Data Normalizers ───────────────────────────────────────────────────

export function normalizeBillableRows(rows: unknown): BillableProductRow[] {
  const list = Array.isArray(rows)
    ? rows
    : Array.isArray((rows as any)?.results)
      ? (rows as any).results
      : [];
  return list
    .map((row: any) => {
      const product = (row?.product ?? null) as Product | null;
      if (!product || typeof product.id !== 'number') {
        return null;
      }

      const pendingApplications = (row?.pendingApplications ??
        row?.pending_applications ??
        []) as DocApplicationInvoice[];
      const pendingApplicationsCount = Number(
        row?.pendingApplicationsCount ??
          row?.pending_applications_count ??
          pendingApplications.length,
      );
      const hasPendingApplications =
        row?.hasPendingApplications ??
        row?.has_pending_applications ??
        pendingApplicationsCount > 0;

      return {
        product,
        pendingApplications: Array.isArray(pendingApplications) ? pendingApplications : [],
        pendingApplicationsCount: Number.isFinite(pendingApplicationsCount)
          ? pendingApplicationsCount
          : 0,
        hasPendingApplications: Boolean(hasPendingApplications),
      } as BillableProductRow;
    })
    .filter((row: BillableProductRow | null): row is BillableProductRow => row !== null);
}

export function toDocApplicationInvoice(value: unknown): DocApplicationInvoice | null {
  if (!value || typeof value !== 'object') {
    return null;
  }

  const candidate = value as Partial<DocApplicationInvoice> & {
    product?: Partial<Product> | null;
  };
  if (typeof candidate.id !== 'number') {
    return null;
  }
  if (!candidate.product || typeof candidate.product.id !== 'number') {
    return null;
  }

  return candidate as DocApplicationInvoice;
}

export function sortBillableRows(rows: BillableProductRow[]): BillableProductRow[] {
  return [...rows].sort((left, right) => {
    if (left.hasPendingApplications !== right.hasPendingApplications) {
      return left.hasPendingApplications ? -1 : 1;
    }
    return (left.product.name ?? '').localeCompare(right.product.name ?? '', undefined, {
      sensitivity: 'base',
    });
  });
}

export function ensureSourceApplicationIncluded(
  rows: BillableProductRow[],
  rawSourceApplication: unknown,
): BillableProductRow[] {
  const sourceApplication = toDocApplicationInvoice(rawSourceApplication);
  const sourceApplicationId = Number(sourceApplication?.id ?? 0);
  const sourceProduct = sourceApplication?.product as Product | null | undefined;
  const sourceProductId = Number(sourceProduct?.id ?? 0);

  if (!sourceApplication || !sourceApplicationId || !sourceProductId || !sourceProduct) {
    return rows;
  }

  const existingRowIndex = rows.findIndex((row) => row.product.id === sourceProductId);
  if (existingRowIndex === -1) {
    return sortBillableRows([
      ...rows,
      {
        product: sourceProduct,
        pendingApplications: [sourceApplication],
        pendingApplicationsCount: 1,
        hasPendingApplications: true,
      },
    ]);
  }

  const existingRow = rows[existingRowIndex];
  if (
    existingRow.pendingApplications.some((application) => application.id === sourceApplicationId)
  ) {
    return rows;
  }

  const updatedRow: BillableProductRow = {
    ...existingRow,
    pendingApplications: [sourceApplication, ...existingRow.pendingApplications],
    pendingApplicationsCount: existingRow.pendingApplicationsCount + 1,
    hasPendingApplications: true,
  };

  return rows.map((row, index) => (index === existingRowIndex ? updatedRow : row));
}
