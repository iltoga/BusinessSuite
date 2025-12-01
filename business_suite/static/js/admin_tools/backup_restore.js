/**
 * @module admin_tools/backup_restore
 * @description Handles database backup functionality including:
 *   - Starting backup process with optional user data inclusion
 *   - Real-time log streaming via EventSource
 *   - Live log display and auto-scrolling
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';

    function initBackupRestore() {
        const startBackupBtn = document.getElementById('start-backup');
        const logElement = document.getElementById('log');
        const includeUsersCheckbox = document.getElementById('include-users');

        if (!startBackupBtn || !logElement) {
            return; // Elements not found, exit gracefully
        }

        startBackupBtn.addEventListener('click', function() {
            // Clear previous log
            logElement.textContent = '';

            // Get include users preference
            const includeUsers = includeUsersCheckbox && includeUsersCheckbox.checked ? '1' : '0';

            // Get backup URL from data attribute
            const backupUrl = startBackupBtn.getAttribute('data-backup-url');
            if (!backupUrl) {
                console.error('Backup URL not found');
                logElement.textContent = 'Error: Backup URL not configured\n';
                return;
            }

            // Create EventSource for real-time log streaming
            const eventSource = new EventSource(backupUrl + '?include_users=' + includeUsers);

            eventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    logElement.textContent += data.message + '\n';
                    // Auto-scroll to bottom
                    logElement.scrollTop = logElement.scrollHeight;
                } catch (err) {
                    console.error('Error parsing log message:', err);
                }
            };

            // When backup finishes update the list via JSON fetch
            eventSource.addEventListener('message', function(e) {
                try {
                    const payload = JSON.parse(e.data);
                    const msg = payload.message || '';
                    if (msg.startsWith('Backup finished') || msg.startsWith('Restore finished')) {
                        // Fetch the updated backups list
                        fetchBackupsList();
                    }
                } catch (err) {
                    // ignore
                }
            });

            eventSource.onerror = function(event) {
                logElement.textContent += 'Connection closed\n';
                eventSource.close();
            };
        });

        // Delete backups handler
        const deleteBackupsBtn = document.getElementById('delete-backups');
        if (deleteBackupsBtn) {
            deleteBackupsBtn.addEventListener('click', function() {
                if (!confirm('Are you sure you want to delete ALL backup files? This action cannot be undone.')) {
                    return;
                }
                const deleteUrl = deleteBackupsBtn.getAttribute('data-delete-url');
                if (!deleteUrl) {
                    logElement.textContent += 'Error: delete URL not configured\n';
                    return;
                }
                // Get CSRF token from cookie
                function getCookie(name) {
                    const value = `; ${document.cookie}`;
                    const parts = value.split(`; ${name}=`);
                    if (parts.length === 2) return parts.pop().split(';').shift();
                }
                const csrftoken = getCookie('csrftoken');

                logElement.textContent += 'Deleting backups...\n';
                fetch(deleteUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrftoken || ''
                    },
                    credentials: 'same-origin'
                })
                .then(resp => resp.json())
                .then(json => {
                    if (json.ok) {
                        logElement.textContent += `Deleted ${json.deleted} files\n`;
                        // reload page to show updated backup list
                        setTimeout(() => { window.location.reload(); }, 500);
                    } else {
                        logElement.textContent += `Error deleting backups: ${json.error}\n`;
                    }
                })
                .catch(err => {
                    logElement.textContent += `Error deleting backups: ${err}\n`;
                });
            });
        }
    }

    function fetchBackupsList() {
        const listEl = document.getElementById('backups-list');
        if (!listEl) return;
        const url = listEl.getAttribute('data-list-url');
        if (!url) return;
        fetch(url, { credentials: 'same-origin' })
            .then(resp => resp.json())
            .then(json => {
                const backups = json.backups || [];
                listEl.innerHTML = '';
                if (!backups.length) {
                    const li = document.createElement('li');
                    li.textContent = 'No backups yet';
                    listEl.appendChild(li);
                    return;
                }
                backups.forEach(b => {
                    const li = document.createElement('li');
                    li.className = 'mb-2';
                    const strong = document.createElement('strong');
                    strong.textContent = b.filename;
                    li.appendChild(strong);
                    const small = document.createElement('small');
                    small.className = 'text-muted ms-2';
                    small.innerHTML = `&ndash; ${b.size ? filesizeFormat(b.size) : 'unknown size'} &ndash; ${b.type}`;
                    li.appendChild(small);
                    if (b.filename.includes('_with_users')) {
                        const badge = document.createElement('span');
                        badge.className = 'badge bg-primary ms-2';
                        badge.textContent = 'Full';
                        li.appendChild(badge);
                    }
                    if (b.included_files) {
                        const filesBadge = document.createElement('span');
                        filesBadge.className = 'badge bg-success ms-2';
                        filesBadge.textContent = `Files: ${b.included_files}`;
                        li.appendChild(filesBadge);
                    }
                    const a = document.createElement('a');
                    a.href = `/admin-tools/backups/${encodeURIComponent(b.filename)}`;
                    a.className = 'ms-2';
                    a.textContent = 'download';
                    li.appendChild(a);
                    listEl.appendChild(li);
                });
            })
            .catch(err => {
                console.error('Error fetching backups list', err);
            });
    }

    // We need a rudimentary file size formatter similar to Django's filesizeformat
    function filesizeFormat(bytes) {
        if (bytes == null) return 'unknown size';
        if (bytes < 1024) return `${bytes} bytes`;
        const kb = Math.round((bytes / 1024) * 10) / 10;
        if (kb < 1024) return `${kb} KB`;
        const mb = Math.round((kb / 1024) * 10) / 10;
        return `${mb} MB`;
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initBackupRestore);
    } else {
        initBackupRestore();
    }
})();
