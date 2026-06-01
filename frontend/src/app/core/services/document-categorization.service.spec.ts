import { firstValueFrom, of } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import {
  DocumentCategorizationService,
  type CategorizationSseEvent,
} from './document-categorization.service';

describe('DocumentCategorizationService.watchCategorizationJob', () => {
  it('reconnects when a complete event arrives before all categorization results are terminal', async () => {
    vi.useFakeTimers();

    const service = Object.create(DocumentCategorizationService.prototype) as any;

    service.sseService = {
      connectMessages: vi
        .fn()
        .mockReturnValueOnce(
          of({
            event: 'complete',
            id: '1',
            data: {
              jobId: 'cat-1',
              results: [
                {
                  itemId: 'item-1',
                  filename: 'passport.pdf',
                  status: 'categorized',
                  pipelineStage: 'validating',
                  aiValidationEnabled: true,
                  documentType: 'Passport',
                  documentTypeId: 12,
                  documentId: 99,
                  confidence: 0.91,
                  reasoning: 'Waiting on validation',
                  error: null,
                  categorizationPass: 1,
                  validationStatus: 'pending',
                  validationReasoning: null,
                  validationNegativeIssues: null,
                },
              ],
            },
          }),
        )
        .mockReturnValueOnce(
          of({
            event: 'complete',
            id: '2',
            data: {
              jobId: 'cat-1',
              results: [
                {
                  itemId: 'item-1',
                  filename: 'passport.pdf',
                  status: 'categorized',
                  pipelineStage: 'validated',
                  aiValidationEnabled: true,
                  documentType: 'Passport',
                  documentTypeId: 12,
                  documentId: 99,
                  confidence: 0.91,
                  reasoning: 'Validation finished',
                  error: null,
                  categorizationPass: 1,
                  validationStatus: 'valid',
                  validationReasoning: null,
                  validationNegativeIssues: null,
                },
              ],
            },
          }),
        ),
    };

    const received: CategorizationSseEvent[] = [];
    const completeSpy = vi.fn();

    service.watchCategorizationJob('cat-1').subscribe({
      next: (event) => {
        received.push(event);
      },
      complete: completeSpy,
    });

    await vi.runAllTimersAsync();

    expect(service.sseService.connectMessages).toHaveBeenCalledTimes(2);
    expect(service.sseService.connectMessages).toHaveBeenNthCalledWith(
      1,
      '/api/document-categorization/stream/cat-1/',
      {
        maxConnectionDurationMs: 55_000,
      },
    );
    expect(received).toEqual([
      {
        type: 'complete',
        data: {
          jobId: 'cat-1',
          results: [
            {
              itemId: 'item-1',
              filename: 'passport.pdf',
              status: 'categorized',
              pipelineStage: 'validating',
              aiValidationEnabled: true,
              documentType: 'Passport',
              documentTypeId: 12,
              documentId: 99,
              confidence: 0.91,
              reasoning: 'Waiting on validation',
              error: null,
              categorizationPass: 1,
              validationStatus: 'pending',
              validationReasoning: null,
              validationNegativeIssues: null,
            },
          ],
        },
      },
      {
        type: 'complete',
        data: {
          jobId: 'cat-1',
          results: [
            {
              itemId: 'item-1',
              filename: 'passport.pdf',
              status: 'categorized',
              pipelineStage: 'validated',
              aiValidationEnabled: true,
              documentType: 'Passport',
              documentTypeId: 12,
              documentId: 99,
              confidence: 0.91,
              reasoning: 'Validation finished',
              error: null,
              categorizationPass: 1,
              validationStatus: 'valid',
              validationReasoning: null,
              validationNegativeIssues: null,
            },
          ],
        },
      },
    ]);
    expect(completeSpy).toHaveBeenCalledTimes(1);
  });

  it('preserves empty validationStatus values when normalizing validate-category responses', async () => {
    const service = Object.create(DocumentCategorizationService.prototype) as any;

    service.documentsApi = {
      documentsValidateCategoryCreate: vi.fn(() =>
        of({
          matches: false,
          expectedType: 'Passport',
          detectedType: 'Passport',
          confidence: 0.42,
          reasoning: 'Needs manual review',
          documentTypeId: 12,
          validationStatus: '',
          validationResult: { negativeIssues: ['Needs review'] },
          aiValidationEnabled: true,
        }),
      ),
    };

    const response = await firstValueFrom(
      service.validateCategory(12, new File(['x'], 'passport.pdf')),
    );

    expect(response.validationStatus).toBe('');
    expect(response.validationResult).toEqual({ negativeIssues: ['Needs review'] });
  });
});
