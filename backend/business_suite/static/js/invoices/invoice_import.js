/* Invoice import (drag & drop) script
   Extracted from invoice_import.html. Reads config from #invoice-import-container data attributes.
*/
(function(){
    'use strict';
    function init(){
        var container = document.getElementById('invoice-import-container');
        if (!container) return;
        var currentProvider = container.dataset.currentProvider || '';
        var currentModel = container.dataset.currentModel || '';
        var llmConfigUrl = container.dataset.llmConfigUrl || '/static/llm_models.json';

        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const fileList = document.getElementById('fileList');
        const fileItems = document.getElementById('fileItems');
        const importBtn = document.getElementById('importBtn');
        const clearBtn = document.getElementById('clearBtn');
        const resultsSummary = document.getElementById('resultsSummary');
        const resultsTable = document.getElementById('resultsTable');
        const resultsTableBody = document.getElementById('resultsTableBody');
        const progressMessage = document.getElementById('progressMessage');
        const progressText = document.getElementById('progressText');
        const llmProviderSelect = document.getElementById('llmProvider');
        const llmModelSelect = document.getElementById('llmModel');

        let selectedFiles = [];
        let eventSource = null;
        let llmModelsConfig = null;

        fetch(llmConfigUrl)
            .then(response => response.json())
            .then(data => {
                llmModelsConfig = data;
                initializeLLMSelects();
            })
            .catch(error => {
                console.error('Error loading LLM models:', error);
                if (llmProviderSelect) llmProviderSelect.innerHTML = '<option value="">Error loading providers</option>';
            });

        function initializeLLMSelects() {
            if (!llmModelsConfig) return;
            llmProviderSelect.innerHTML = '<option value="">Use system default</option>';
            Object.keys(llmModelsConfig.providers).forEach(providerId => {
                const provider = llmModelsConfig.providers[providerId];
                const option = document.createElement('option');
                option.value = providerId;
                option.textContent = provider.name;
                if (providerId === currentProvider) option.selected = true;
                llmProviderSelect.appendChild(option);
            });
            updateModelDropdown();
        }

        llmProviderSelect.addEventListener('change', updateModelDropdown);

        function updateModelDropdown(){
            const selectedProvider = llmProviderSelect.value;
            if (!selectedProvider || !llmModelsConfig){
                llmModelSelect.innerHTML = '<option value="">Use system default</option>';
                return;
            }
            const provider = llmModelsConfig.providers[selectedProvider];
            if (!provider) { llmModelSelect.innerHTML = '<option value="">Invalid provider</option>'; return; }
            llmModelSelect.innerHTML = '<option value="">Use system default</option>';
            provider.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id; option.textContent = model.name; option.title = model.description;
                if (selectedProvider === currentProvider && model.id === currentModel) option.selected = true;
                llmModelSelect.appendChild(option);
            });
        }

        // Continue with event handlers and helper functions (displayFiles, handleFiles, SSE import, etc.)
        function displayFiles() {
            if (!fileItems) return;
            fileItems.innerHTML = '';

            if (!selectedFiles || selectedFiles.length === 0) {
                if (fileList) fileList.style.display = 'none';
                return;
            }

            if (fileList) fileList.style.display = 'block';

            selectedFiles.forEach((file, index) => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.id = `file-item-${index}`;
                fileItem.innerHTML = `
                    <div>
                        <i class="bi bi-file-earmark"></i>
                        <strong>${file.name}</strong>
                        <small class="text-muted ms-2">(${formatFileSize(file.size)})</small>
                        <div class="file-detail" id="file-detail-${index}"></div>
                    </div>
                    <div>
                        <span class="badge bg-warning text-dark status-badge" id="status-${index}">Pending</span>
                        <div class="form-check form-check-inline ms-2">
                            <input class="form-check-input mark-paid-checkbox" type="checkbox" id="paid-${index}" data-index="${index}">
                            <label class="form-check-label" for="paid-${index}" title="Mark this invoice as paid upon import">
                                <i class="bi bi-cash-coin"></i> Paid
                            </label>
                        </div>
                        <button class="btn btn-sm btn-danger ms-2 remove-btn" data-index="${index}">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                `;
                fileItems.appendChild(fileItem);
            });

            // Add remove button handlers
            document.querySelectorAll('.remove-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const index = parseInt(e.currentTarget.getAttribute('data-index'));
                    selectedFiles.splice(index, 1);
                    displayFiles();
                });
            });
        }

        function formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        }

        function handleFiles(files) {
            selectedFiles = Array.from(files);
            displayFiles();
        }

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            handleFiles(files);
        }

        // Import button handler using streaming response reading
        const importUrl = container.dataset.batchImportUrl || container.dataset.batchImport || '/';
        importBtn && importBtn.addEventListener('click', async () => {
            if (!selectedFiles || selectedFiles.length === 0) return;

            importBtn.disabled = true;
            clearBtn && (clearBtn.disabled = true);
            progressMessage && progressMessage.classList.add('active');

            const selectedProvider = llmProviderSelect ? llmProviderSelect.value : '';
            const selectedModel = llmModelSelect ? llmModelSelect.value : '';

            if (selectedProvider && selectedModel) {
                const providerName = llmProviderSelect.options[llmProviderSelect.selectedIndex].text;
                const modelName = llmModelSelect.options[llmModelSelect.selectedIndex].text;
                progressText && (progressText.textContent = `Starting import with ${providerName} - ${modelName}...`);
            } else {
                progressText && (progressText.textContent = 'Starting import with default AI model...');
            }

            document.querySelectorAll('.remove-btn').forEach(btn => btn.disabled = true);

            const formData = new FormData();
            selectedFiles.forEach((file, index) => {
                formData.append('files', file);
                const paidCheckbox = document.getElementById(`paid-${index}`);
                const isPaid = paidCheckbox && paidCheckbox.checked ? 'true' : 'false';
                formData.append('paid_status', isPaid);
            });

            if (selectedProvider) formData.append('llm_provider', selectedProvider);
            if (selectedModel) formData.append('llm_model', selectedModel);

            const csrfEl = document.querySelector('[name=csrfmiddlewaretoken]');
            const csrfToken = csrfEl ? csrfEl.value : '';

            try {
                const response = await fetch(importUrl, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken },
                    body: formData
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const events = buffer.split('\n\n');
                    buffer = events.pop();
                    events.forEach(eventText => {
                        if (!eventText.trim()) return;
                        const lines = eventText.split('\n');
                        let eventType = 'message';
                        let eventData = '';
                        lines.forEach(line => {
                            if (line.startsWith('event: ')) eventType = line.substring(7);
                            else if (line.startsWith('data: ')) eventData = line.substring(6);
                        });
                        if (eventData) {
                            try { const data = JSON.parse(eventData); handleSSEEvent(eventType, data); } catch(e) { console.error('Error parsing event data:', e); }
                        }
                    });
                }

            } catch (error) {
                console.error('Error:', error);
                progressText && (progressText.textContent = '✗ Error: ' + error.message);
                alert('Error uploading files: ' + error.message);
            } finally {
                importBtn.disabled = false;
                clearBtn && (clearBtn.disabled = false);
            }
        });

        function handleSSEEvent(eventType, data) {
            console.log('SSE Event:', eventType, data);
            switch(eventType) {
                case 'start':
                    progressText && (progressText.textContent = data.message);
                    break;
                case 'file_start':
                    progressText && (progressText.textContent = data.message);
                    updateFileStatus(data.index - 1, 'processing', 'Processing...', 'bg-warning');
                    break;
                case 'parsing':
                    progressText && (progressText.textContent = data.message);
                    updateFileDetail(data.index - 1, '🤖 Parsing with AI...');
                    break;
                case 'file_success':
                    updateFileStatus(data.index - 1, 'success', 'Imported', 'bg-success');
                    updateFileDetail(data.index - 1, `✓ Customer: ${data.result.customer?.name || 'N/A'}<br>Invoice: ${data.result.invoice?.invoice_no || 'N/A'}`);
                    break;
                case 'file_duplicate':
                    updateFileStatus(data.index - 1, 'duplicate', 'Duplicate', 'bg-warning');
                    updateFileDetail(data.index - 1, '⚠ This invoice already exists');
                    break;
                case 'file_error':
                    updateFileStatus(data.index - 1, 'error', 'Error', 'bg-danger');
                    updateFileDetail(data.index - 1, `✗ ${data.result.message || 'Unknown error'}`);
                    break;
                case 'complete':
                    progressText && (progressText.textContent = data.message);
                    progressMessage && progressMessage.classList.remove('active');
                    displayResults(data);
                    break;
                default:
                    console.warn('Unknown SSE event:', eventType);
            }
        }

        function updateFileStatus(index, className, statusText, badgeClass) {
            const fileItem = document.getElementById(`file-item-${index}`);
            const statusBadge = document.getElementById(`status-${index}`);
            if (fileItem) fileItem.className = `file-item ${className}`;
            if (statusBadge) { statusBadge.className = `badge ${badgeClass}`; statusBadge.textContent = statusText; }
        }

        function updateFileDetail(index, detailHTML, errors = null) {
            const detail = document.getElementById(`file-detail-${index}`);
            if (detail) {
                detail.innerHTML = detailHTML;
                if (errors && errors.length > 0) {
                    const errorList = document.createElement('ul');
                    errorList.className = 'text-danger mt-2 mb-0 small';
                    errorList.style.paddingLeft = '20px';
                    errors.forEach(err => { const li = document.createElement('li'); li.textContent = err; errorList.appendChild(li); });
                    detail.appendChild(errorList);
                }
            }
        }

        clearBtn && clearBtn.addEventListener('click', () => {
            selectedFiles = [];
            if (fileInput) fileInput.value = '';
            displayFiles();
            resultsSummary && (resultsSummary.style.display = 'none');
            resultsTable && (resultsTable.style.display = 'none');
            progressMessage && progressMessage.classList.remove('active');
        });

        function displayResults(data) {
            document.getElementById('totalCount').textContent = data.summary.total;
            document.getElementById('importedCount').textContent = data.summary.imported;
            document.getElementById('duplicateCount').textContent = data.summary.duplicates;
            document.getElementById('errorCount').textContent = data.summary.errors;
            resultsSummary && (resultsSummary.style.display = 'block');
            resultsTableBody && (resultsTableBody.innerHTML = '');
            data.results.forEach(result => {
                const row = document.createElement('tr');
                let badgeClass = 'bg-secondary'; let badgeText = result.status;
                if (result.status === 'imported') { badgeClass = 'bg-success'; badgeText = 'Imported'; }
                else if (result.status === 'duplicate') { badgeClass = 'bg-warning'; badgeText = 'Duplicate'; }
                else if (result.status === 'error') { badgeClass = 'bg-danger'; badgeText = 'Error'; }
                const filenameCell = document.createElement('td'); filenameCell.textContent = result.filename; row.appendChild(filenameCell);
                const statusCell = document.createElement('td'); statusCell.innerHTML = `<span class="badge ${badgeClass}">${badgeText}</span>`; row.appendChild(statusCell);
                const detailsCell = document.createElement('td');
                if (result.status === 'imported' && result.invoice) {
                    detailsCell.innerHTML = `
                        <strong>${result.invoice.invoice_no}</strong><br>
                        Customer: ${result.invoice.customer_name}<br>
                        Amount: ${result.invoice.total_amount}<br>
                        <a href="${result.invoice.url}" target="_blank" class="btn btn-sm btn-primary mt-1"><i class="bi bi-eye"></i> View Invoice</a>
                    `;
                } else {
                    detailsCell.innerHTML = result.message;
                    if (result.errors && result.errors.length > 0) {
                        const errorList = document.createElement('ul');
                        errorList.className = 'text-danger mt-2 mb-0 small'; errorList.style.paddingLeft = '20px';
                        result.errors.forEach(err => { const li = document.createElement('li'); li.textContent = err; errorList.appendChild(li); });
                        detailsCell.appendChild(errorList);
                    }
                }
                row.appendChild(detailsCell);
                resultsTableBody.appendChild(row);
            });
            resultsTable && (resultsTable.style.display = 'block');
        }

        // Initialize drag/drop and change handlers
        if (dropZone) {
            ['dragenter','dragover','dragleave','drop'].forEach(ev => { dropZone.addEventListener(ev, preventDefaults, false); document.body.addEventListener(ev, preventDefaults, false); });
            ['dragenter','dragover'].forEach(ev => dropZone.addEventListener(ev, () => dropZone.classList.add('drag-over'), false));
            ['dragleave','drop'].forEach(ev => dropZone.addEventListener(ev, () => dropZone.classList.remove('drag-over'), false));
            dropZone.addEventListener('click', () => fileInput && fileInput.click());
            dropZone.addEventListener('drop', handleDrop, false);
        }
        fileInput && fileInput.addEventListener('change', (e) => handleFiles(e.target.files));
    }

    if (document.readyState !== 'loading') init(); else document.addEventListener('DOMContentLoaded', init);
})();
