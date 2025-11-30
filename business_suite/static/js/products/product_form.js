/**
 * @module products/product_form
 * @description Handles product form interactions including:
 *   - Dynamic task form management (add/remove)
 *   - Task form indexing and renaming
 *   - Default task values for visa products
 *   - Document validity synchronization
 * @requires jQuery
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';

    /**
     * Initialize the product form functionality
     */
    function initProductForm() {
        // Add task button handler
        const addTaskBtn = document.getElementById('add-task');
        if (addTaskBtn) {
            addTaskBtn.addEventListener('click', handleAddTask, false);
        }

        // Remove task button handler (delegated event)
        $(document).on('click', '.remove-task-btn', handleRemoveTask);

        // Document validity synchronization
        const validityField = document.getElementById('id_validity');
        if (validityField) {
            $(validityField).on('change', handleValidityChange);
        }
    }

    /**
     * Handle adding a new task form
     */
    function handleAddTask() {
        const formIdx = $('#id_tasks-TOTAL_FORMS').val();
        const emptyFormHtml = $('#empty-form').html();
        const newTaskForm = emptyFormHtml.replace(/__prefix__/g, formIdx);
        
        $('#task-form-list').append(newTaskForm);
        $('#id_tasks-TOTAL_FORMS').val(parseInt(formIdx) + 1);
        $('#id_tasks-' + formIdx + '-step').val(parseInt(formIdx) + 1);

        // If product type is 'visa', set default values for the first task form
        const productType = $('#id_product_type').val();
        if (productType === 'visa' && formIdx === '0') {
            $('#id_tasks-' + formIdx + '-name').val('Document Collection');
            $('#id_tasks-' + formIdx + '-description').val('Collecting documents from Customer');
        }
    }

    /**
     * Handle removing a task form
     */
    function handleRemoveTask() {
        if ($('.task-form').length > 1) {
            $(this).parent().remove();
            updateTaskFormIndices();
        }
    }

    /**
     * Update task form indices after removal
     */
    function updateTaskFormIndices() {
        const forms = $('#task-form-list .task-form');
        $('#id_tasks-TOTAL_FORMS').val(forms.length);
        
        let i = 0;
        for (const form of forms.toArray()) {
            $(form).find('input,select,checkbox').each(function() {
                const nameAttr = $(this).attr('name');
                const idAttr = $(this).attr('id');
                
                if (nameAttr) {
                    $(this).attr('name', nameAttr.replace(/-\d+-/, '-' + i + '-'));
                }
                if (idAttr) {
                    $(this).attr('id', idAttr.replace(/-\d+-/, '-' + i + '-'));
                }
            });
            i++;
        }
    }

    /**
     * Handle validity field change - sync with documents_min_validity
     */
    function handleValidityChange() {
        const validityValue = $(this).val();
        $('#id_documents_min_validity').val(validityValue);
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initProductForm);
    } else {
        initProductForm();
    }
})();
