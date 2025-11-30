/**
 * @module customer_applications/docworkflow_form
 * @description Handles document workflow form interactions including:
 *   - Automatic due date calculation based on start date
 *   - API integration for due date computation
 *   - Error handling and display
 * @requires utils.js
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';
    
    /**
     * Initializes the document workflow form functionality
     */
    function initDocWorkflowForm() {
        const startDateField = document.getElementById('id_start_date');
        
        if (!startDateField) {
            console.warn('Start date field not found on page');
            return;
        }
        
        // Get task ID and URL template from data attributes
        const form = document.getElementById('doc-workflow-step-form');
        if (!form) {
            console.error('Document workflow form not found');
            return;
        }
        
        const taskId = form.dataset.taskId;
        const urlTemplate = form.dataset.dueDateUrl;
        
        if (!taskId || !urlTemplate) {
            console.error('Missing task ID or URL template in form data attributes');
            return;
        }
        
        // Add event listener for start date changes
        startDateField.addEventListener('change', function(e) {
            const startDate = new Date(e.target.value);
            const startDateStr = startDate.toISOString().split('T')[0];
            
            // Build the API URL by replacing placeholders
            let url = urlTemplate;
            url = url.replace('12345', taskId);
            url = url.replace('67890', startDateStr);
            
            // Make API call to compute due date
            restApiCall('GET', url, null,
                function(data) {
                    // Parse and format the due date
                    const dueDate = new Date(data.due_date);
                    const dueDateStr = dueDate.toISOString().split('T')[0];
                    setFormFieldValue('id_due_date', dueDateStr);
                },
                function(error) {
                    // Display error message
                    toggleMessageDisplay(false, error.message, 'due_date_error_id', '');
                }
            );
        });
    }
    
    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDocWorkflowForm);
    } else {
        initDocWorkflowForm();
    }
})();
