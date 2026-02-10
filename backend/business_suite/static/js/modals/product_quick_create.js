/**
 * @module modals/product_quick_create
 * @description Handles product quick create modal interactions including:
 *   - Modal initialization and display
 *   - Select2 initialization for document type fields
 *   - Form submission via AJAX
 *   - Dynamic product addition to target select elements
 *   - Error handling and display
 * @requires jQuery
 * @requires Select2
 * @requires Bootstrap 5
 * @requires utils.js (for showSuccessMessage)
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';

    var $modal = $('#productQuickCreateModal');
    var $form = $('#productQuickCreateForm');
    var $submitBtn = $('#productQuickCreateSubmitBtn');
    var $errors = $('#productQuickCreateErrors');
    var targetSelectId = null; // Will store the ID of the select element to update

    /**
     * Initializes the product quick create modal
     * Sets up Select2 for document type fields
     */
    function initProductQuickCreateModal() {
        // Initialize select2 for document types
        $('#id_quick_required_documents, #id_quick_optional_documents').select2({
            theme: 'bootstrap-5',
            dropdownParent: $modal,
            placeholder: 'Select documents',
        });

        // Handle form submission
        $form.on('submit', handleFormSubmit);

        // Reset form when modal is hidden
        $modal.on('hidden.bs.modal', resetModal);
    }

    /**
     * Opens the product quick create modal
     * @param {string} selectElementId - The ID of the select element to update after product creation
     */
    window.openProductQuickCreateModal = function(selectElementId) {
        targetSelectId = selectElementId;
        $form[0].reset();
        $errors.addClass('d-none').html('');
        $('#id_quick_required_documents, #id_quick_optional_documents').val([]).trigger('change');
        $modal.modal('show');

        // Ensure this modal's backdrop is on top
        setTimeout(function() {
            var $backdrop = $('.modal-backdrop').last();
            $backdrop.css('z-index', 1064);
        }, 50);
    };

    /**
     * Handles form submission
     * @param {Event} e - The form submit event
     */
    function handleFormSubmit(e) {
        e.preventDefault();
        $errors.addClass('d-none').html('');
        $submitBtn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Creating...');

        // Prepare data - convert multi-select to comma-separated strings
        var formData = new FormData($form[0]);
        var requiredDocs = $('#id_quick_required_documents').val();
        var optionalDocs = $('#id_quick_optional_documents').val();

        // Remove the multiple entries and add as single comma-separated values
        formData.delete('required_documents');
        formData.delete('optional_documents');
        formData.append('required_documents', requiredDocs ? requiredDocs.join(', ') : '');
        formData.append('optional_documents', optionalDocs ? optionalDocs.join(', ') : '');

        $.ajax({
            url: $form.data('url') || '/api/products/quick-create/',
            method: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            headers: {
                'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]', $form).val()
            },
            success: handleSubmitSuccess,
            error: handleSubmitError,
            complete: function() {
                $submitBtn.prop('disabled', false).html('<i class="fas fa-save"></i> Create Product');
            }
        });
    }

    /**
     * Handles successful form submission
     * @param {Object} response - The AJAX response object
     */
    function handleSubmitSuccess(response) {
        if (response.success) {
            // Add new product to target select
            if (targetSelectId) {
                var $targetSelect = $('#' + targetSelectId);
                var newOption = new Option(
                    response.product.code + ' - ' + response.product.name,
                    response.product.id,
                    true,
                    true
                );
                $targetSelect.append(newOption).trigger('change');
            }

            // Close modal and reset form
            $modal.modal('hide');
            $form[0].reset();

            // Show success message
            if (typeof showSuccessMessage === 'function') {
                showSuccessMessage('Product created successfully!');
            } else if (typeof showSuccessToast === 'function') {
                showSuccessToast('Product created successfully!');
            } else {
                alert('Product created successfully!');
            }
        } else {
            // Show errors
            displayErrors(response.errors);
        }
    }

    /**
     * Handles form submission errors
     * @param {Object} xhr - The XMLHttpRequest object
     */
    function handleSubmitError(xhr) {
        var errorMsg = 'An error occurred while creating the product.';
        if (xhr.responseJSON && xhr.responseJSON.error) {
            errorMsg = xhr.responseJSON.error;
        }
        $errors.html(errorMsg).removeClass('d-none');
    }

    /**
     * Displays validation errors in the modal
     * @param {Object} errors - Object containing field errors
     */
    function displayErrors(errors) {
        var errorHtml = '<ul class="mb-0">';
        $.each(errors, function(field, fieldErrors) {
            $.each(fieldErrors, function(i, error) {
                errorHtml += '<li><strong>' + field + ':</strong> ' + error + '</li>';
            });
        });
        errorHtml += '</ul>';
        $errors.html(errorHtml).removeClass('d-none');
    }

    /**
     * Resets the modal to its initial state
     */
    function resetModal() {
        $form[0].reset();
        $errors.addClass('d-none').html('');
        $('#id_quick_required_documents, #id_quick_optional_documents').val([]).trigger('change');
        targetSelectId = null;
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initProductQuickCreateModal);
    } else {
        initProductQuickCreateModal();
    }
})();
