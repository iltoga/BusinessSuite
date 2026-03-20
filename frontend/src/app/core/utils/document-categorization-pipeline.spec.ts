import { describe, expect, it } from 'vitest';

import {
  getCategorizationValidationBadge,
  getDocumentAiValidationBadge,
  isCategorizationPipelineTerminal,
} from './document-categorization-pipeline';

describe('isCategorizationPipelineTerminal', () => {
  it('keeps AI-validated matches pending until validation reaches a terminal status', () => {
    expect(
      isCategorizationPipelineTerminal({
        status: 'categorized',
        pipelineStage: 'categorized',
        aiValidationEnabled: true,
        validationStatus: null,
        documentId: 42,
      }),
    ).toBe(false);

    expect(
      isCategorizationPipelineTerminal({
        status: 'categorized',
        pipelineStage: 'validating',
        aiValidationEnabled: true,
        validationStatus: 'pending',
        documentId: 42,
      }),
    ).toBe(false);
  });

  it('treats categorized no-slot results as terminal even without validation state', () => {
    expect(
      isCategorizationPipelineTerminal({
        status: 'categorized',
        pipelineStage: 'categorized',
        aiValidationEnabled: null,
        validationStatus: null,
        documentId: null,
      }),
    ).toBe(true);
  });

  it('treats successful, invalid, and failed validations as terminal states', () => {
    expect(
      isCategorizationPipelineTerminal({
        status: 'categorized',
        pipelineStage: 'validated',
        aiValidationEnabled: true,
        validationStatus: 'valid',
      }),
    ).toBe(true);

    expect(
      isCategorizationPipelineTerminal({
        status: 'categorized',
        pipelineStage: 'validated',
        aiValidationEnabled: true,
        validationStatus: 'invalid',
      }),
    ).toBe(true);

    expect(
      isCategorizationPipelineTerminal({
        status: 'categorized',
        pipelineStage: 'validated',
        aiValidationEnabled: true,
        validationStatus: 'error',
      }),
    ).toBe(true);
  });

  it('uses the same processing badge for validation while the pipeline step is running', () => {
    expect(
      getCategorizationValidationBadge({
        status: 'categorized',
        pipelineStage: 'validating',
        aiValidationEnabled: true,
        validationStatus: 'pending',
      }),
    ).toEqual({
      label: 'Processing...',
      type: 'secondary',
      showSpinner: true,
    });
  });

  it('prefers live categorization pipeline validation state over persisted document state', () => {
    expect(
      getDocumentAiValidationBadge(
        { aiValidationStatus: null },
        {
          status: 'categorized',
          pipelineStage: 'validating',
          aiValidationEnabled: true,
          documentId: 42,
          validationStatus: 'pending',
        },
      ),
    ).toEqual({
      label: 'Processing...',
      type: 'secondary',
      showSpinner: true,
    });
  });
});
