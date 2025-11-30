/**
 * Invoice Update Page JavaScript
 * 
 * Handles invoice update page functionality including:
 * - Creating new customer applications from the invoice update page
 * - Adding invoice application rows dynamically
 * - Managing the relationship between invoices and customer applications
 * 
 * @module invoices/invoice_update
 * @requires jQuery
 * @requires Select2
 * @requires utils.js
 * @requires invoices/invoice_form.js
 */

(function() {
    'use strict';

    /**
     * Initialize the invoice update page
     */
    function initInvoiceUpdate() {
        // Handle Create New Application button
        $(document).on('click', '#create-new-application-btn', function() {
            if (window.currentCustomer) {
                openCustomerApplicationQuickCreateModal(window.currentCustomer, window.currentCustomerName);
            } else {
                alert('No customer found for this invoice.');
            }
        });

        // Make addInvoiceApplicationRow available globally for the modal callback
        window.addInvoiceApplicationRow = addInvoiceApplicationRow;
    }

    /**
     * Adds a new invoice application row with the created application
     * This function is called from the customer application quick create modal
     * after a new application is successfully created
     * 
     * @param {Object} application - The newly created application object
     * @param {number} application.id - The application ID
     * @param {string} application.display_name - The display name for the application
     * @param {string} application.product_name - The product name
     * @param {string} application.product_code - The product code
     * @param {string} application.customer_name - The customer name
     * @param {number} application.base_price - The base price
     * @param {string} application.doc_date - The document date
     */
    function addInvoiceApplicationRow(application) {
        // First, add the application to the customerApplications array
        window.customerApplications.push({
            pk: application.id,
            fields: {
                product: {
                    base_price: application.base_price,
                    name: application.product_name,
                    code: application.product_code
                },
                customer: {
                    full_name: application.customer_name
                },
                doc_date: application.doc_date
            }
        });

        // Add the new application as an option to ALL customer application dropdowns
        $('select[name$="-customer_application"]').each(function() {
            var $select = $(this);
            // Check if option already exists
            if ($select.find('option[value="' + application.id + '"]').length === 0) {
                var newOption = new Option(application.display_name, application.id, false, false);
                $select.append(newOption);
            }
        });

        // Now create a new form row and select the new application
        var $formList = $('#invoiceapplication-form-list');
        var $emptyForm = $('#empty-form');
        var totalForms = $('#id_invoice_applications-TOTAL_FORMS');
        var formIdx = parseInt(totalForms.val());

        // Clone the empty form
        var newForm = $emptyForm.html().replace(/__prefix__/g, formIdx);
        var $newFormDiv = $('<div class="invoiceapplication_form p-3 mb-4 border rounded"></div>');
        $newFormDiv.html(newForm);

        // Append to form list
        $formList.append($newFormDiv);

        // Initialize select2 for the new form
        $newFormDiv.find('select[name$="-customer_application"]').select2({
            theme: 'bootstrap-5',
            width: '100%'
        });

        // Set the customer application
        var $appSelect = $newFormDiv.find('select[name$="-customer_application"]');
        $appSelect.val(application.id).trigger('change');

        // Set the amount
        var $amountInput = $newFormDiv.find('input[name$="-amount"]');
        $amountInput.val(application.base_price.toFixed(window.decimals));

        // Hide DELETE checkbox for new forms
        $newFormDiv.find('input[name$="-DELETE"]').parent().hide();

        // Increment form count
        totalForms.val(formIdx + 1);

        // Bind remove button
        $newFormDiv.find('.remove-invoiceapplication-btn').on('click', function() {
            $newFormDiv.remove();
        });
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initInvoiceUpdate);
    } else {
        initInvoiceUpdate();
    }
})();
