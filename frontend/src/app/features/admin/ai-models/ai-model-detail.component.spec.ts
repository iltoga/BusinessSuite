import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';

import { AiModelsService } from '@/core/api/api/ai-models.service';
import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';

import { AiModelDetailComponent } from './ai-model-detail.component';

describe('AiModelDetailComponent', () => {
  let component: AiModelDetailComponent;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        {
          provide: AiModelsService,
          useValue: {
            aiModelsRetrieve: vi.fn(),
            aiModelsDestroy: vi.fn(),
          },
        },
        { provide: Router, useValue: { navigate: vi.fn() } },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: {
                get: vi.fn(() => null),
              },
            },
          },
        },
        {
          provide: GlobalToastService,
          useValue: {
            success: vi.fn(),
            error: vi.fn(),
          },
        },
        { provide: AuthService, useValue: { isSuperuser: vi.fn(() => false) } },
        { provide: PLATFORM_ID, useValue: 'browser' },
      ],
    });

    component = TestBed.runInInjectionContext(() => new AiModelDetailComponent());
  });

  it('renders pricing rows from pricingDisplay values without extra scaling', () => {
    component.item.set({
      id: 19,
      provider: 'openrouter',
      modelId: 'openrouter/qwen3.5-flash',
      name: 'Qwen: Qwen3.5-Flash',
      description: 'Test model',
      vision: true,
      fileUpload: false,
      reasoning: true,
      contextLength: 32768,
      maxCompletionTokens: 8192,
      modality: 'text->text',
      architectureModality: 'text->text',
      architectureTokenizer: 'qwen',
      instructType: 'chat',
      promptPricePerToken: '0.00000016',
      completionPricePerToken: '0.00000130',
      imagePrice: '0',
      requestPrice: '0.00000005',
      topProviderId: 'openrouter',
      providerName: 'OpenRouter',
      supportedParameters: ['temperature'],
      perRequestLimits: { maxInputTokens: 4096 },
      source: 'manual',
      rawMetadata: { id: 'openrouter/qwen3.5-flash' },
      capabilities: { vision: true, fileUpload: false, reasoning: true },
      pricingDisplay: {
        promptPricePerMillionTokens: '0.16',
        completionPricePerMillionTokens: '1.3',
        imagePricePerMillionTokens: '0',
        requestPricePerMillionTokens: '0.05',
      },
      architecture: { modality: 'text->text', tokenizer: 'qwen', instructType: 'chat' },
      createdAt: '2026-03-05T21:48:07Z',
      updatedAt: '2026-03-08T22:05:16Z',
    } as any);

    expect(component.pricingRows()).toEqual([
      { label: 'Prompt Price (per 1M tokens)', value: '0.16' },
      { label: 'Completion Price (per 1M tokens)', value: '1.30' },
      { label: 'Image Price (per 1M tokens)', value: '0.00' },
      { label: 'Request Price (per 1M tokens)', value: '0.05' },
    ]);
  });
});
