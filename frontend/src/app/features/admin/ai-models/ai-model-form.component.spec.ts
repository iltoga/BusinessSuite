import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { of } from 'rxjs';

import { AiModelsService } from '@/core/api/api/ai-models.service';
import { GlobalToastService } from '@/core/services/toast.service';

import { AiModelFormComponent } from './ai-model-form.component';

describe('AiModelFormComponent', () => {
  let component: AiModelFormComponent;
  let aiModelsApiMock: {
    aiModelsRetrieve: ReturnType<typeof vi.fn>;
    aiModelsCreate: ReturnType<typeof vi.fn>;
    aiModelsUpdate: ReturnType<typeof vi.fn>;
    aiModelsDestroy: ReturnType<typeof vi.fn>;
    aiModelsOpenrouterSearchRetrieve: ReturnType<typeof vi.fn>;
  };
  let routerMock: { navigate: ReturnType<typeof vi.fn> };
  let routeMock: {
    snapshot: {
      paramMap: {
        get: ReturnType<typeof vi.fn>;
      };
    };
  };
  let toastMock: { success: ReturnType<typeof vi.fn>; error: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    aiModelsApiMock = {
      aiModelsRetrieve: vi.fn(),
      aiModelsCreate: vi.fn(),
      aiModelsUpdate: vi.fn(),
      aiModelsDestroy: vi.fn(),
      aiModelsOpenrouterSearchRetrieve: vi.fn(),
    };
    routerMock = {
      navigate: vi.fn(),
    };
    routeMock = {
      snapshot: {
        paramMap: {
          get: vi.fn(() => null),
        },
      },
    };
    toastMock = {
      success: vi.fn(),
      error: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        { provide: AiModelsService, useValue: aiModelsApiMock },
        { provide: Router, useValue: routerMock },
        { provide: ActivatedRoute, useValue: routeMock },
        { provide: GlobalToastService, useValue: toastMock },
        { provide: PLATFORM_ID, useValue: 'browser' },
      ],
    });

    component = TestBed.runInInjectionContext(() => new AiModelFormComponent());
  });

  it('populates pricing inputs from pricingDisplay values without rescaling', () => {
    component['populateForm']({
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
      pricingDisplay: {
        promptPricePerMillionTokens: '0.16',
        completionPricePerMillionTokens: '1.3',
        imagePricePerMillionTokens: '0',
        requestPricePerMillionTokens: '0.05',
      },
    } as any);

    expect(component.form.get('prompt_price_per_token')?.value).toBe('0.16');
    expect(component.form.get('completion_price_per_token')?.value).toBe('1.30');
    expect(component.form.get('image_price')?.value).toBe('0.00');
    expect(component.form.get('request_price')?.value).toBe('0.05');
  });

  it('loads and patches pricing inputs when editing an existing model', () => {
    aiModelsApiMock.aiModelsRetrieve.mockReturnValue(
      of({
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
        topProviderId: 'openrouter',
        providerName: 'OpenRouter',
        supportedParameters: ['temperature'],
        perRequestLimits: { maxInputTokens: 4096 },
        source: 'manual',
        rawMetadata: { id: 'openrouter/qwen3.5-flash' },
        pricingDisplay: {
          promptPricePerMillionTokens: '0.16',
          completionPricePerMillionTokens: '1.3',
          imagePricePerMillionTokens: '0',
          requestPricePerMillionTokens: '0.05',
        },
      } as any),
    );

    routeMock.snapshot.paramMap.get.mockImplementation((key: string) => (key === 'id' ? '19' : null));

    component.ngOnInit();

    expect(aiModelsApiMock.aiModelsRetrieve).toHaveBeenCalledWith({ id: 19 });
    expect(component.form.get('model_id')?.value).toBe('openrouter/qwen3.5-flash');
    expect(component.form.get('provider_name')?.value).toBe('OpenRouter');
    expect(component.form.get('top_provider_id')?.value).toBe('openrouter');
    expect(component.form.get('prompt_price_per_token')?.value).toBe('0.16');
    expect(component.form.get('completion_price_per_token')?.value).toBe('1.30');
    expect(component.form.get('image_price')?.value).toBe('0.00');
    expect(component.form.get('request_price')?.value).toBe('0.05');
  });

  it('uses pricingDisplay values when a model is selected', () => {
    component.onModelSelected({
      value: 'openrouter/qwen3.5-flash',
      label: 'Qwen: Qwen3.5-Flash',
      model: {
        provider: 'openrouter',
        model_id: 'openrouter/qwen3.5-flash',
        modelId: 'openrouter/qwen3.5-flash',
        name: 'Qwen: Qwen3.5-Flash',
        pricingDisplay: {
          promptPricePerMillionTokens: '0.16',
          completionPricePerMillionTokens: '1.3',
          imagePricePerMillionTokens: '0',
          requestPricePerMillionTokens: '0.05',
        },
      },
    } as any);

    expect(component.form.get('prompt_price_per_token')?.value).toBe('0.16');
    expect(component.form.get('completion_price_per_token')?.value).toBe('1.30');
    expect(component.form.get('image_price')?.value).toBe('0.00');
    expect(component.form.get('request_price')?.value).toBe('0.05');
  });

  it('unwraps the API envelope when loading OpenRouter models', () => {
    aiModelsApiMock.aiModelsOpenrouterSearchRetrieve.mockReturnValue(
      of({
        data: {
          results: [
            {
              provider: 'openrouter',
              model_id: 'openrouter/qwen3.5-flash',
              name: 'Qwen: Qwen3.5-Flash',
              pricingDisplay: {
                promptPricePerMillionTokens: '0.16',
                completionPricePerMillionTokens: '1.3',
                imagePricePerMillionTokens: '0',
                requestPricePerMillionTokens: '0.05',
              },
            },
          ],
        },
      } as any),
    );

    component['loadModels']('qwen');

    expect(aiModelsApiMock.aiModelsOpenrouterSearchRetrieve).toHaveBeenCalledWith({
      limit: 10,
      q: 'qwen',
    });
    expect(component.modelOptions()).toHaveLength(1);
    expect(component.modelOptions()[0].label).toBe('Qwen: Qwen3.5-Flash');
    expect(component.modelOptions()[0].model.pricingDisplay?.promptPricePerMillionTokens).toBe(
      '0.16',
    );
  });

  it('converts display prices back to per-token storage values on submit payload creation', () => {
    component.form.patchValue({
      provider: 'openrouter',
      model_id: 'openrouter/qwen3.5-flash',
      name: 'Qwen: Qwen3.5-Flash',
      prompt_price_per_token: '0.16',
      completion_price_per_token: '1.30',
      image_price: '0.00',
      request_price: '0.05',
    });

    const dto = component['createDto']();

    expect(Number(dto.promptPricePerToken)).toBeCloseTo(1.6e-7, 12);
    expect(Number(dto.completionPricePerToken)).toBeCloseTo(1.3e-6, 12);
    expect(dto.imagePrice).toBe('0');
    expect(Number(dto.requestPrice)).toBeCloseTo(5e-8, 12);
  });
});
