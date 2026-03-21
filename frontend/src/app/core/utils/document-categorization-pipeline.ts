export type CategorizationValidationStatus = 'valid' | 'invalid' | 'pending' | 'error' | null;

export type PipelineBadgeType =
  | 'default'
  | 'secondary'
  | 'outline'
  | 'success'
  | 'warning'
  | 'destructive';

export interface PipelineBadgeState {
  label: string;
  type: PipelineBadgeType;
  showSpinner: boolean;
}

export interface CategorizationPipelineStateLike {
  status: string;
  pipelineStage?: string | null;
  aiValidationEnabled?: boolean | null;
  validationStatus?: CategorizationValidationStatus;
  documentId?: number | null;
}

export interface DocumentAiValidationStateLike {
  aiValidationStatus?: string | null;
}

export function isCategorizationPipelineTerminal(
  result: CategorizationPipelineStateLike,
): boolean {
  if (result.status === 'error' || result.pipelineStage === 'error') {
    return true;
  }

  if (result.status !== 'categorized') {
    return false;
  }

  // No-slot files are finished as soon as categorization resolves: there is
  // nothing left to validate or apply in the application.
  if (result.documentId == null) {
    return true;
  }

  if (result.aiValidationEnabled === false) {
    return result.pipelineStage === 'categorized' || result.pipelineStage === 'validated';
  }

  return isValidationStatusTerminal(result.validationStatus ?? null);
}

export function getCategorizationResultStatusBadge(
  result: CategorizationPipelineStateLike,
): PipelineBadgeState {
  if (result.status === 'error' || result.pipelineStage === 'error') {
    return { label: 'Error', type: 'destructive', showSpinner: false };
  }

  if (
    result.status === 'uploading' ||
    result.status === 'queued' ||
    result.status === 'processing' ||
    result.pipelineStage === 'uploading' ||
    result.pipelineStage === 'uploaded' ||
    result.pipelineStage === 'categorizing' ||
    result.pipelineStage === 'validating'
  ) {
    return getProcessingBadgeState();
  }

  if (result.status === 'categorized' && result.documentId) {
    return { label: 'Matched', type: 'success', showSpinner: false };
  }

  if (result.status === 'categorized') {
    return { label: 'No Slot', type: 'warning', showSpinner: false };
  }

  return { label: 'Queued', type: 'secondary', showSpinner: false };
}

export function getCategorizationValidationBadge(
  result: CategorizationPipelineStateLike,
): PipelineBadgeState | null {
  if (
    result.pipelineStage === 'validating' ||
    result.validationStatus === 'pending' ||
    (result.aiValidationEnabled !== false &&
      result.status === 'categorized' &&
      !isCategorizationPipelineTerminal(result))
  ) {
    return getProcessingBadgeState();
  }

  if (result.validationStatus === 'valid') {
    return { label: 'Valid', type: 'success', showSpinner: false };
  }

  if (result.validationStatus === 'invalid') {
    return { label: 'Invalid', type: 'destructive', showSpinner: false };
  }

  if (result.validationStatus === 'error') {
    return { label: 'Error', type: 'destructive', showSpinner: false };
  }

  return null;
}

export function getDocumentAiValidationBadge(
  document: DocumentAiValidationStateLike,
  activePipelineResult?: CategorizationPipelineStateLike | null,
): PipelineBadgeState | null {
  const pipelineBadge =
    activePipelineResult && activePipelineResult.documentId
      ? getCategorizationValidationBadge(activePipelineResult)
      : null;
  if (pipelineBadge) {
    return pipelineBadge;
  }

  switch ((document.aiValidationStatus ?? '').trim().toLowerCase()) {
    case 'pending':
    case 'validating':
      return getProcessingBadgeState();
    case 'valid':
      return { label: 'Valid', type: 'success', showSpinner: false };
    case 'invalid':
      return { label: 'Invalid', type: 'destructive', showSpinner: false };
    case 'error':
      return { label: 'Error', type: 'destructive', showSpinner: false };
    default:
      return null;
  }
}

function getProcessingBadgeState(): PipelineBadgeState {
  return { label: 'Processing...', type: 'secondary', showSpinner: true };
}

function isValidationStatusTerminal(status: CategorizationValidationStatus): boolean {
  return status === 'valid' || status === 'invalid' || status === 'error';
}
