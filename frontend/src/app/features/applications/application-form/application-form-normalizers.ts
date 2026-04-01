import { parseApiDate } from '@/shared/utils/date-parsing';

// ── Interfaces ─────────────────────────────────────────────────────────

export interface ApplicationDocumentTypeOption {
  id: number;
  name: string;
  isStayPermit: boolean;
}

export interface ApplicationCalendarTaskOption {
  id: number;
  step: number;
  name: string;
  addTaskToCalendar: boolean;
}

export interface ProductDocumentsAdapter {
  requiredDocuments: ApplicationDocumentTypeOption[];
  optionalDocuments: ApplicationDocumentTypeOption[];
  tasks: ApplicationCalendarTaskOption[];
  calendarTask: ApplicationCalendarTaskOption | null;
}

export interface ApplicationFormSnapshot {
  customerId: number | null;
  productId: number | null;
  docDate: Date;
  dueDate: Date;
  addDeadlinesToCalendar: boolean;
  notifyCustomer: boolean;
  notifyCustomerChannel: 'whatsapp' | 'email';
  notes: string;
}

export interface ApplicationFormNavigationState {
  from?: string;
  focusId?: number | null;
  searchQuery?: string | null;
  returnUrl?: string;
  customerId?: number;
  page?: number;
  returnToList?: boolean;
  awaitPassportImport?: boolean;
}

// ── Type Coercion Helpers ──────────────────────────────────────────────

export function toRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

export function toNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

// ── Data Normalizers ───────────────────────────────────────────────────

export function adaptApplicationSnapshot(raw: unknown): ApplicationFormSnapshot {
  const source = toRecord(raw);
  const docDate = parseApiDate(source?.['docDate']) ?? new Date();
  const dueDate = parseApiDate(source?.['dueDate']) ?? docDate;
  const notifyCustomerRaw = source?.['notifyCustomer'] ?? source?.['notifyCustomerToo'];
  const notifyChannelRaw = source?.['notifyCustomerChannel'];
  const notifyCustomerChannel: 'whatsapp' | 'email' =
    notifyChannelRaw === 'email' ? 'email' : 'whatsapp';

  return {
    customerId: toNumber(source?.['customer'] ?? toRecord(source?.['customer'])?.['id']),
    productId: toNumber(source?.['product'] ?? toRecord(source?.['product'])?.['id']),
    docDate,
    dueDate,
    addDeadlinesToCalendar: Boolean(source?.['addDeadlinesToCalendar'] ?? true),
    notifyCustomer: Boolean(notifyCustomerRaw),
    notifyCustomerChannel,
    notes: typeof source?.['notes'] === 'string' ? source['notes'] : '',
  };
}

export function adaptDocumentTypes(raw: unknown): ApplicationDocumentTypeOption[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((entry) => toRecord(entry))
    .filter((entry): entry is Record<string, unknown> => !!entry)
    .map((entry) => ({
      id: toNumber(entry['id']) ?? 0,
      name: typeof entry['name'] === 'string' ? entry['name'] : '',
      isStayPermit: Boolean(entry['isStayPermit'] ?? entry['is_stay_permit']),
    }))
    .filter((entry) => entry.id > 0 && entry.name.length > 0);
}

export function adaptProductDocuments(raw: unknown): ProductDocumentsAdapter {
  const source = toRecord(raw);
  const productContainer = toRecord(source?.['product']) ?? source;
  const explicitTask = adaptCalendarTask(source?.['calendarTask']);

  const tasks = Array.isArray(productContainer?.['tasks'])
    ? (productContainer['tasks'] as unknown[])
        .map((task) => adaptCalendarTask(task))
        .filter((task): task is ApplicationCalendarTaskOption => !!task)
    : [];

  const calendarTask = explicitTask ?? tasks.find((task) => task.addTaskToCalendar) ?? null;

  return {
    requiredDocuments: adaptDocumentTypes(source?.['requiredDocuments']),
    optionalDocuments: adaptDocumentTypes(source?.['optionalDocuments']),
    tasks,
    calendarTask,
  };
}

export function adaptCalendarTask(raw: unknown): ApplicationCalendarTaskOption | null {
  const source = toRecord(raw);
  if (!source) {
    return null;
  }
  const id = toNumber(source['id']);
  if (!id) {
    return null;
  }
  return {
    id,
    step: toNumber(source['step']) ?? 0,
    name: typeof source['name'] === 'string' ? source['name'] : '',
    addTaskToCalendar: Boolean(source['addTaskToCalendar']),
  };
}

export function getTaskName(task: ApplicationCalendarTaskOption | null): string | null {
  const rawName = typeof task?.name === 'string' ? task.name.trim() : '';
  return rawName || null;
}

export function getCalendarTaskFromProduct(product: unknown): ApplicationCalendarTaskOption | null {
  const adapted = adaptProductDocuments(product);
  if (adapted.calendarTask) {
    return adapted.calendarTask;
  }
  if (!adapted.tasks.length) {
    return null;
  }
  const sortedTasks = [...adapted.tasks].sort((a, b) => a.step - b.step);
  return sortedTasks[0] ?? null;
}

export function shouldAwaitPassportImport(application: unknown): boolean {
  const raw = toRecord(application);
  if (!raw) {
    return false;
  }

  const product = toRecord(raw['product']);
  const documents = Array.isArray(raw['documents']) ? raw['documents'] : [];
  const configuredDocumentNames = new Set(
    [
      ...parseDocumentNames(product?.['requiredDocuments']),
      ...parseDocumentNames(product?.['optionalDocuments']),
    ].map((name) => name.toLowerCase()),
  );

  if (!configuredDocumentNames.has('passport')) {
    return false;
  }

  return !documents.some((document) => {
    const rawDocument = toRecord(document);
    const docType = toRecord(rawDocument?.['docType'] ?? rawDocument?.['doc_type']);
    const docTypeName = docType?.['name'];
    return typeof docTypeName === 'string' && docTypeName.trim().toLowerCase() === 'passport';
  });
}

export function parseDocumentNames(value: unknown): string[] {
  if (typeof value !== 'string' || !value.trim()) {
    return [];
  }
  return value
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}
