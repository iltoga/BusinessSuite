/**
 * @module modals/customer_application_quick_create
 * @description Handles customer application quick create modal interactions including:
 *   - Modal initialization and display
 *   - Select2 initialization for product fields
 *   - Dynamic product loading via AJAX
 *   - Form submission via AJAX
 *   - Integration with invoice applications formset
 *   - Error handling and display
 * @requires jQuery
 * @requires Select2
 * @requires Bootstrap 5
 * @requires utils.js (for getCookie)
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';

    var $modal = $('#customerApplicationQuickCreateModal');
    var $form = $('#customerApplicationQuickCreateForm');
    var $submitBtn = $('#customerApplicationQuickCreateSubmitBtn');
    var $errors = $('#customerApplicationQuickCreateErrors');
    var customerId = null;
    var customerName = '';

    /**
     * Initializes Select2 for the product dropdown
     */
    function initializeProductSelect2() {
        var $productSelect = $('#id_quick_app_product');

        // Destroy existing select2 if it exists
        if ($productSelect.hasClass('select2-hidden-accessible')) {
            $productSelect.select2('destroy');
        }

        // Initialize select2 with proper configuration
        $productSelect.select2({
            dropdownParent: $modal,
            width: '100%',
            theme: 'bootstrap-5',
            placeholder: 'Select a product',
        });
    }

    /**
     * Loads products via AJAX and populates the product dropdown
     */
    function loadProducts() {
        var $productSelect = $('#id_quick_app_product');
        $productSelect.empty();
        $productSelect.append('<option value="">---------</option>');
        
        $.ajax({
            url: '/api/products/',
            method: 'GET',
            success: function(data) {
                $.each(data, function(i, product) {
                    $productSelect.append(
                        $('<option></option>').val(product.id).text(product.code + ' - ' + product.name)
                    );
                });
                // Only initialize select2 after options are loaded
                initializeProductSelect2();
            },
            error: function(xhr, status, error) {
                console.error('Failed to load products:', error);
                // Still initialize select2 even if loading fails
                initializeProductSelect2();
            }
        });
    }

    /**
     * Sets today's date as the default application date
     */
    function setDefaultDate() {
        var today = new Date().toISOString().split('T')[0];
        $('#id_quick_app_doc_date').val(today);
    }

    /**
     * Opens the customer application quick create modal
     * @param {number} custId - The customer ID
     * @param {string} custName - The customer name
     */
    window.openCustomerApplicationQuickCreateModal = function(custId, custName) {
        customerId = custId;
        customerName = custName;
        $('#id_quick_app_customer').val(customerId);
        $('#customer-name-display').text(customerName);

        // Reset form fields (but don't use form.reset() which can break select2)
        $('#id_quick_app_product').val('');
        $('#id_quick_app_notes').val('');
        $('#id_quick_app_customer').val(customerId);
        setDefaultDate();
        $errors.addClass('d-none').html('');

        // Ensure products are loaded and select2 is initialized
        loadProducts();

        $modal.modal('show');

        // Ensure this modal's backdrop is on top
        setTimeout(function() {
            var $backdrop = $('.modal-backdrop').last();
            $backdrop.css('z-index', 1059);
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

        // Get CSRF token
        var csrftoken = $('input[name="csrfmiddlewaretoken"]', $form).val();
        if (!csrftoken) {
            // Fallback: try to get from cookie using utils.js function
            csrftoken = getCookie('csrftoken');
        }

        $.ajax({
            url: $form.data('url') || '/api/customer-applications/quick-create/',
            type: 'POST',
            data: $form.serialize(),
            headers: {
                'X-CSRFToken': csrftoken
            },
            success: handleSubmitSuccess,
            error: handleSubmitError,
            complete: function() {
                $submitBtn.prop('disabled', false).html('<i class="fas fa-save"></i> Create Application');
            }
        });
    }

    /**
     * Handles successful form submission
     * @param {Object} response - The AJAX response object
     */
    function handleSubmitSuccess(response) {
        if (response.success) {
            // Add new application to the invoice applications formset
            if (typeof addInvoiceApplicationRow === 'function') {
                addInvoiceApplicationRow(response.application);
            }

            // Close modal and reset form
            $modal.modal('hide');
            $form[0].reset();

            // Intentionally do NOT show any confirmation (toast/alert)
            // for quick-creates — simply close the modal silently.
        } else {
            // Show errors
            displayErrors(response);
        }
    }

    /**
     * Handles form submission errors
     * @param {Object} xhr - The XMLHttpRequest object
     */
    function handleSubmitError(xhr) {
        var errorMsg = 'An error occurred while creating the customer application.';
        if (xhr.responseJSON && xhr.responseJSON.error) {
            errorMsg = xhr.responseJSON.error;
        }
        $errors.html(errorMsg).removeClass('d-none');
    }

    /**
     * Displays validation errors in the modal
     * @param {Object} response - Response object containing errors
     */
    function displayErrors(response) {
        var errorHtml = '<ul class="mb-0">';
        if (response.errors) {
            $.each(response.errors, function(field, errors) {
                if (Array.isArray(errors)) {
                    $.each(errors, function(i, error) {
                        errorHtml += '<li><strong>' + field + ':</strong> ' + error + '</li>';
                    });
                } else {
                    errorHtml += '<li><strong>' + field + ':</strong> ' + errors + '</li>';
                }
            });
        } else if (response.error) {
            errorHtml += '<li>' + response.error + '</li>';
        }
        errorHtml += '</ul>';
        $errors.html(errorHtml).removeClass('d-none');
    }

    /**
     * Resets the modal to its initial state
     */
    function resetModal() {
        var today = new Date().toISOString().split('T')[0];
        // Clear form fields without using form.reset() to preserve select2
        $('#id_quick_app_product').val('').trigger('change');
        $('#id_quick_app_notes').val('');
        $('#id_quick_app_doc_date').val(today);
        $('#id_quick_app_customer').val('');
        $errors.addClass('d-none').html('');
    }

    /**
     * Handles the product creation button click
     * Opens the product quick create modal if available
     */
    function handleProductCreateClick() {
        if (typeof openProductQuickCreateModal === 'function') {
            openProductQuickCreateModal('id_quick_app_product');
        }
    }

    /**
     * Initializes the customer application quick create modal
     * Sets up event handlers and loads initial data
     */
    function initCustomerApplicationQuickCreateModal() {
        // Load products on page load
        loadProducts();

        // Set today's date as default
        setDefaultDate();

        // Handle product creation button
        $('.btn-add-product-from-app').on('click', handleProductCreateClick);

        // Handle form submission
        $form.on('submit', handleFormSubmit);

        // Reset form when modal is hidden
        $modal.on('hidden.bs.modal', resetModal);
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCustomerApplicationQuickCreateModal);
    } else {
        initCustomerApplicationQuickCreateModal();
    }
})();
