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
            
            eventSource.onerror = function(event) {
                logElement.textContent += 'Connection closed\n';
                eventSource.close();
            };
        });
    }
    
    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initBackupRestore);
    } else {
        initBackupRestore();
    }
})();
