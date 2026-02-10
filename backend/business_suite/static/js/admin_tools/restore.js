/**
 * @module admin_tools/restore
 * @description Handles database restore functionality including:
 *   - Restoring from existing backup files
 *   - Uploading and restoring from new backup files
 *   - Live log streaming via EventSource
 *   - Progress tracking for upload and restore
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
        const uploadProgressContainer = document.getElementById('upload-progress-container');
        const uploadProgressBar = document.getElementById('upload-progress-bar');
        const uploadStatus = document.getElementById('upload-status');
        const cancelUploadBtn = document.getElementById('cancel-upload');
        const restoreProgressContainer = document.getElementById('restore-progress-container');
        const restoreProgressBar = document.getElementById('restore-progress-bar');

        let currentXhr = null;

        if (!log) {
            console.error('Log element not found');
            return;
        }

        /**
         * Format bytes to human readable format
         */
        function formatBytes(bytes, decimals = 2) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const dm = decimals < 0 ? 0 : decimals;
            const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
        }

        /**
         * Start restore process and stream logs via EventSource
         * @param {string} filename - Name of the backup file to restore
         */
        function startRestore(filename) {
            log.textContent = '';
            restoreProgressContainer.classList.remove('d-none');
            restoreProgressBar.style.width = '0%';
            restoreProgressBar.textContent = '0%';

            const restoreUrl = startRestoreBtn.dataset.restoreUrl;
            const includeUsers = document.getElementById('include-users') && document.getElementById('include-users').checked ? '1' : '0';
            const es = new EventSource(restoreUrl + '?file=' + encodeURIComponent(filename) + '&include_users=' + includeUsers);

            es.onmessage = function(e) {
                try {
                    const data = JSON.parse(e.data);
                    if (data.progress) {
                        const prog = data.progress + '%';
                        restoreProgressBar.style.width = prog;
                        restoreProgressBar.textContent = prog;
                    } else if (data.message) {
                        log.textContent += data.message + '\n';
                        log.scrollTop = log.scrollHeight;
                    }
                } catch (err) {
                    // Ignore parsing errors for non-JSON data (like keepalives if they weren't comments)
                }
            };

            es.onerror = function(e) {
                log.textContent += 'Connection closed\n';
                es.close();
                // We keep the progress bar at its last state or hide if finished
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

        // Cancel upload
        if (cancelUploadBtn) {
            cancelUploadBtn.addEventListener('click', function() {
                if (currentXhr) {
                    currentXhr.abort();
                    log.textContent += 'Upload cancelled by user.\n';
                    uploadProgressContainer.classList.add('d-none');
                    const uploadBtn = document.getElementById('upload-restore-btn');
                    uploadBtn.disabled = false;
                    uploadBtn.textContent = 'Upload and Restore';
                }
            });
        }

        // Upload and restore
        if (uploadForm) {
            uploadForm.addEventListener('submit', function(e) {
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
                uploadProgressContainer.classList.remove('d-none');
                log.textContent = 'Starting upload...\n';

                const formData = new FormData();
                formData.append('backup_file', file);

                const xhr = new XMLHttpRequest();
                currentXhr = xhr;

                xhr.upload.addEventListener('progress', function(e) {
                    if (e.lengthComputable) {
                        const percentComplete = Math.round((e.loaded / e.total) * 100);
                        uploadProgressBar.style.width = percentComplete + '%';
                        uploadProgressBar.textContent = percentComplete + '%';
                        uploadStatus.textContent = `Uploaded ${formatBytes(e.loaded)} of ${formatBytes(e.total)}`;
                    }
                });

                xhr.addEventListener('load', function() {
                    currentXhr = null;
                    try {
                        const result = JSON.parse(xhr.responseText);
                        if (xhr.status === 200 && result.ok) {
                            log.textContent += 'Upload complete: ' + result.filename + '\n';
                            log.textContent += 'Starting restore...\n';
                            uploadProgressContainer.classList.add('d-none');
                            startRestore(result.filename);
                        } else {
                            log.textContent += 'Upload failed: ' + (result.error || 'Server error') + '\n';
                            uploadBtn.disabled = false;
                            uploadBtn.textContent = 'Upload and Restore';
                        }
                    } catch (err) {
                        log.textContent += 'Error processing server response.\n';
                        uploadBtn.disabled = false;
                        uploadBtn.textContent = 'Upload and Restore';
                    }
                });

                xhr.addEventListener('error', function() {
                    currentXhr = null;
                    log.textContent += 'Upload failed due to a network error.\n';
                    uploadBtn.disabled = false;
                    uploadBtn.textContent = 'Upload and Restore';
                });

                xhr.addEventListener('abort', function() {
                    currentXhr = null;
                    // Already handled in cancel button click
                });

                xhr.open('POST', uploadUrl);
                xhr.setRequestHeader('X-CSRFToken', csrfToken.value);
                xhr.send(formData);
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
