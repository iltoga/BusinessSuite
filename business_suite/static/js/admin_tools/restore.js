/**
 * @module admin_tools/restore
 * @description Handles database restore functionality including:
 *   - Restoring from existing backup files
 *   - Uploading and restoring from new backup files
 *   - Live log streaming via EventSource
 * @validates Requirements 2.1, 2.3
 */

(function() {
    'use strict';

    /**
     * Initialize restore page functionality
     */
    function initRestorePage() {
        const log = document.getElementById('log');
        const startRestoreBtn = document.getElementById('start-restore');
        const uploadForm = document.getElementById('upload-form');

        if (!log) {
            console.error('Log element not found');
            return;
        }

        /**
         * Start restore process and stream logs via EventSource
         * @param {string} filename - Name of the backup file to restore
         */
        function startRestore(filename) {
            log.textContent = '';
            const restoreUrl = startRestoreBtn.dataset.restoreUrl;
            const es = new EventSource(restoreUrl + '?file=' + encodeURIComponent(filename));
            
            es.onmessage = function(e) {
                try {
                    const data = JSON.parse(e.data);
                    log.textContent += data.message + '\n';
                    log.scrollTop = log.scrollHeight;
                } catch (err) {
                    console.error('Error parsing message:', err);
                }
            };
            
            es.onerror = function(e) {
                log.textContent += 'Connection closed\n';
                es.close();
            };
        }

        // Restore from existing backup
        if (startRestoreBtn) {
            startRestoreBtn.addEventListener('click', function() {
                const backupSelect = document.getElementById('backup-select');
                const file = backupSelect ? backupSelect.value : '';
                
                if (!file) {
                    alert('Please select a backup file');
                    return;
                }
                
                startRestore(file);
            });
        }

        // Upload and restore
        if (uploadForm) {
            uploadForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const fileInput = document.getElementById('backup-file');
                const file = fileInput ? fileInput.files[0] : null;
                
                if (!file) {
                    alert('Please select a file');
                    return;
                }

                const uploadBtn = document.getElementById('upload-restore-btn');
                const uploadUrl = uploadForm.dataset.uploadUrl;
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
                
                if (!uploadBtn || !uploadUrl || !csrfToken) {
                    console.error('Required elements not found');
                    return;
                }

                uploadBtn.disabled = true;
                uploadBtn.textContent = 'Uploading...';
                log.textContent = 'Uploading backup file...\n';

                const formData = new FormData();
                formData.append('backup_file', file);

                try {
                    const response = await fetch(uploadUrl, {
                        method: 'POST',
                        body: formData,
                        headers: {
                            'X-CSRFToken': csrfToken.value
                        }
                    });

                    const result = await response.json();
                    
                    if (result.ok) {
                        log.textContent += 'Upload complete: ' + result.filename + '\n';
                        log.textContent += 'Starting restore...\n';
                        startRestore(result.filename);
                    } else {
                        log.textContent += 'Upload failed: ' + result.error + '\n';
                    }
                } catch (err) {
                    log.textContent += 'Upload error: ' + err + '\n';
                } finally {
                    uploadBtn.disabled = false;
                    uploadBtn.textContent = 'Upload and Restore';
                }
            });
        }
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initRestorePage);
    } else {
        initRestorePage();
    }
})();
