import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { InvoicesService } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardIconComponent, type ZardIcon } from '@/shared/components/icon';
import { mergeClasses } from '@/shared/utils/merge-classes';

/** LLM Model configuration */
interface LLMModel {
  id: string;
  name: string;
  description: string;
}

interface LLMProvider {
  name: string;
  models: LLMModel[];
}

interface LLMConfig {
  providers: Record<string, LLMProvider>;
  currentProvider: string;
  currentModel: string;
  maxWorkers: number;
  supportedFormats: string[];
}

/** File item for display */
interface FileItem {
  file: File;
  status: 'pending' | 'processing' | 'parsing' | 'success' | 'duplicate' | 'error';
  statusMessage: string;
  isPaid: boolean;
  result?: ImportResult;
}

/** Single import result from backend */
interface ImportResult {
  success: boolean;
  status: string;
  message: string;
  filename: string;
  invoice?: {
    id: number;
    invoiceNo: string;
    customerName: string;
    totalAmount: string;
    invoiceDate: string;
    status: string;
    url: string;
  };
  customer?: {
    id: number;
    name: string;
    email?: string;
    phone?: string;
  };
  errors?: string[];
}

/** SSE message types */
interface SSEStartMessage {
  total: number;
  message: string;
}

interface SSEFileMessage {
  index: number;
  filename: string;
  message: string;
  result?: ImportResult;
}

interface SSECompleteMessage {
  message: string;
  summary: {
    total: number;
    imported: number;
    duplicates: number;
    errors: number;
  };
  results: ImportResult[];
}

@Component({
  selector: 'app-invoice-import',
  standalone: true,
  imports: [CommonModule, FormsModule, ZardButtonComponent, ZardBadgeComponent, ZardIconComponent],
  templateUrl: './invoice-import.component.html',
  styleUrls: ['./invoice-import.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceImportComponent implements OnInit {
  private destroyRef = inject(DestroyRef);
  private invoicesApi = inject(InvoicesService);
  private toast = inject(GlobalToastService);
  private router = inject(Router);

  // State
  readonly llmConfig = signal<LLMConfig | null>(null);
  readonly isLoadingConfig = signal(false);
  readonly selectedProvider = signal('');
  readonly selectedModel = signal('');
  readonly files = signal<FileItem[]>([]);
  readonly isImporting = signal(false);
  readonly importProgress = signal('');
  readonly isDragOver = signal(false);
  readonly showResults = signal(false);

  // Computed
  readonly hasFiles = computed(() => this.files().length > 0);
  readonly providerOptions = computed(() => {
    const config = this.llmConfig();
    if (!config) return [];
    return Object.entries(config.providers).map(([id, provider]) => ({
      id,
      name: provider.name,
    }));
  });

  readonly modelOptions = computed(() => {
    const config = this.llmConfig();
    const provider = this.selectedProvider();
    if (!config || !provider) return [];
    return config.providers[provider]?.models ?? [];
  });

  readonly importSummary = computed(() => {
    const fileList = this.files();
    return {
      total: fileList.length,
      imported: fileList.filter((f) => f.status === 'success').length,
      duplicates: fileList.filter((f) => f.status === 'duplicate').length,
      errors: fileList.filter((f) => f.status === 'error').length,
    };
  });

  readonly canImport = computed(() => {
    return this.hasFiles() && !this.isImporting();
  });

  constructor() {
    effect(() => {
      const config = this.llmConfig();
      const providerId = this.selectedProvider();

      if (!config || !providerId) {
        if (this.selectedModel()) {
          this.selectedModel.set('');
        }
        return;
      }

      const models = config.providers[providerId]?.models ?? [];
      if (!models.length) {
        if (this.selectedModel()) {
          this.selectedModel.set('');
        }
        return;
      }

      const currentModel = this.selectedModel();
      const isValid = models.some((model) => model.id === currentModel);
      if (!isValid) {
        const defaultModel =
          config.currentProvider === providerId &&
          models.some((model) => model.id === config.currentModel)
            ? config.currentModel
            : '';
        this.selectedModel.set(defaultModel);
      }
    });
  }

  ngOnInit(): void {
    this.loadConfig();
  }

  goBack(): void {
    if (!this.isImporting()) {
      this.router.navigate(['/invoices']);
    }
  }

  private loadConfig(): void {
    this.isLoadingConfig.set(true);

    this.invoicesApi.invoicesImportConfigRetrieve().subscribe({
      next: (response) => {
        const config = response as LLMConfig;
        this.llmConfig.set(config);
        this.selectedProvider.set(config.currentProvider ?? '');
        this.selectedModel.set(config.currentModel ?? '');
        this.isLoadingConfig.set(false);
      },
      error: (error) => {
        console.error('Failed to load import config:', error);
        this.toast.error('Failed to load import configuration');
        this.isLoadingConfig.set(false);
      },
    });
  }

  // File handling
  onFileSelect(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files) {
      this.addFiles(Array.from(input.files));
      input.value = ''; // Reset to allow selecting same files again
    }
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
    const files = event.dataTransfer?.files;
    if (files) {
      this.addFiles(Array.from(files));
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(true);
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
  }

  private addFiles(newFiles: File[]): void {
    const config = this.llmConfig();
    const supportedFormats = config?.supportedFormats ?? ['.pdf', '.xlsx', '.xls', '.docx', '.doc'];

    const validFiles = newFiles.filter((f) => {
      const ext = '.' + f.name.split('.').pop()?.toLowerCase();
      return supportedFormats.includes(ext);
    });

    const invalidCount = newFiles.length - validFiles.length;
    if (invalidCount > 0) {
      this.toast.error(
        `${invalidCount} file(s) skipped - unsupported format. Supported: ${supportedFormats.join(', ')}`,
      );
    }

    const items: FileItem[] = validFiles.map((file) => ({
      file,
      status: 'pending' as const,
      statusMessage: 'Pending',
      isPaid: false,
    }));

    this.files.update((current) => [...current, ...items]);
  }

  removeFile(index: number): void {
    this.files.update((current) => current.filter((_, i) => i !== index));
  }

  togglePaid(index: number): void {
    this.files.update((current) =>
      current.map((f, i) => (i === index ? { ...f, isPaid: !f.isPaid } : f)),
    );
  }

  clearFiles(): void {
    this.files.set([]);
    this.showResults.set(false);
  }

  onProviderChange(providerId: string): void {
    this.selectedProvider.set(providerId);
  }

  onModelChange(modelId: string): void {
    this.selectedModel.set(modelId);
  }

  // Import handling
  startImport(): void {
    if (!this.canImport()) return;

    this.isImporting.set(true);
    this.importProgress.set('Preparing to import...');

    const fileList = this.files();
    const formData = new FormData();

    // Add files and paid status
    fileList.forEach((item, index) => {
      formData.append('files', item.file);
      formData.append('paid_status', item.isPaid ? 'true' : 'false');
    });

    // Add LLM config
    if (this.selectedProvider()) {
      formData.append('llm_provider', this.selectedProvider());
    }
    if (this.selectedModel()) {
      formData.append('llm_model', this.selectedModel());
    }

    // Start SSE import directly with credentials
    this.startSSEImport(formData);
  }

  private startSSEImport(formData: FormData): void {
    const apiBaseUrl = '/api';
    const url = `${apiBaseUrl}/invoices/import/batch/`;

    fetch(url, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No response body');
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Parse SSE events
          const events = buffer.split('\n\n');
          buffer = events.pop() ?? '';

          for (const eventText of events) {
            if (!eventText.trim()) continue;

            const lines = eventText.split('\n');
            let eventType = 'message';
            let eventData = '';

            for (const line of lines) {
              if (line.startsWith('event: ')) {
                eventType = line.substring(7);
              } else if (line.startsWith('data: ')) {
                eventData = line.substring(6);
              }
            }

            if (eventData) {
              try {
                const data = JSON.parse(eventData);
                this.handleSSEEvent(eventType, data);
              } catch (e) {
                console.error('Error parsing SSE data:', e);
              }
            }
          }
        }
      })
      .catch((error) => {
        console.error('Import error:', error);
        this.toast.error('Import failed: ' + error.message);
        this.isImporting.set(false);
      });
  }

  private handleSSEEvent(eventType: string, data: unknown): void {
    switch (eventType) {
      case 'start':
        const startData = data as SSEStartMessage;
        this.importProgress.set(startData.message);
        break;

      case 'file_start':
        const fileStartData = data as SSEFileMessage;
        this.importProgress.set(fileStartData.message);
        this.updateFileStatus(fileStartData.index - 1, 'processing', 'Processing...');
        break;

      case 'parsing':
        const parsingData = data as SSEFileMessage;
        this.importProgress.set(parsingData.message);
        this.updateFileStatus(parsingData.index - 1, 'parsing', 'Parsing with AI...');
        break;

      case 'file_success':
        const successData = data as SSEFileMessage;
        this.updateFileStatus(
          successData.index - 1,
          'success',
          'Imported successfully',
          successData.result,
        );
        break;

      case 'file_duplicate':
        const dupData = data as SSEFileMessage;
        this.updateFileStatus(dupData.index - 1, 'duplicate', 'Duplicate invoice', dupData.result);
        break;

      case 'file_error':
        const errorData = data as SSEFileMessage;
        this.updateFileStatus(
          errorData.index - 1,
          'error',
          errorData.result?.message ?? 'Import failed',
          errorData.result,
        );
        break;

      case 'complete':
        const completeData = data as SSECompleteMessage;
        this.importProgress.set(completeData.message);
        this.isImporting.set(false);
        this.showResults.set(true);
        this.toast.success(
          `Import complete: ${completeData.summary.imported} imported, ` +
            `${completeData.summary.duplicates} duplicates, ${completeData.summary.errors} errors`,
        );
        break;

      default:
        console.warn('Unknown SSE event:', eventType);
    }
  }

  private updateFileStatus(
    index: number,
    status: FileItem['status'],
    statusMessage: string,
    result?: ImportResult,
  ): void {
    this.files.update((current) =>
      current.map((f, i) => (i === index ? { ...f, status, statusMessage, result } : f)),
    );
  }

  viewInvoice(invoiceId: number): void {
    this.router.navigate(['/invoices', invoiceId]);
  }

  // Utilities
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  }

  getStatusBadgeVariant(
    status: FileItem['status'],
  ): 'default' | 'secondary' | 'success' | 'warning' | 'destructive' {
    switch (status) {
      case 'success':
        return 'success';
      case 'duplicate':
        return 'warning';
      case 'error':
        return 'destructive';
      case 'processing':
      case 'parsing':
        return 'secondary';
      default:
        return 'default';
    }
  }

  getStatusIcon(status: FileItem['status']): ZardIcon {
    switch (status) {
      case 'success':
        return 'check';
      case 'duplicate':
        return 'triangle-alert';
      case 'error':
        return 'x';
      case 'processing':
      case 'parsing':
        return 'loader-circle';
      default:
        return 'clock';
    }
  }

  getDropzoneClasses(): string {
    return mergeClasses(
      'flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 text-center transition cursor-pointer',
      this.isDragOver() && !this.isImporting()
        ? 'border-primary bg-primary/5'
        : 'border-muted hover:border-primary/50',
      this.isImporting() ? 'opacity-50 cursor-not-allowed' : '',
    );
  }
}
