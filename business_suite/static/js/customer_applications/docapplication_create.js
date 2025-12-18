/**
 * @module customer_applications/docapplication_create
 * @description Handles document application creation form interactions including:
 *   - Customer and product select2 initialization
 *   - Dynamic document form management (add/remove)
 *   - Product-based required/optional document loading
 *   - Form validation and field enabling/disabling
 * @requires jQuery
 * @requires select2
 * @requires utils.js (restApiCall)
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';

    /**
     * Initialize the document application create form
     */
    function initDocApplicationCreate() {
        initializeSelect2Fields();
        setupCustomerChangeHandler();
        setupProductChangeHandler();
        setupAddDocumentHandler();
        setupRemoveDocumentHandler();
        setupDocTypeChangeHandler();
    }

    /**
     * Initialize select2 for customer and product fields
     */
    function initializeSelect2Fields() {
        // Reinitialize select2 with proper theme for customer field
        $('#id_customer').select2('destroy').select2({
            theme: 'bootstrap-5',
            placeholder: 'Select a customer',
            width: '100%'
        });

        // Reinitialize select2 with proper theme for product field
        $('#id_product').select2('destroy').select2({
            theme: 'bootstrap-5',
            placeholder: 'Select a product',
            width: '100%',
            disabled: false  // Keep enabled so options are visible
        });

        // Check initial state after select2 is initialized
        checkCustomerSelected();
    }

    /**
     * Check if customer is selected and enable/disable dependent fields
     */
    function checkCustomerSelected() {
        var hasCustomer = $('#id_customer').val();
        if (hasCustomer) {
            // Enable product field and add document button
            $('#id_product').prop('disabled', false);
            $('#id_product').select2('enable');
            $('#add-document').prop('disabled', false);
        } else {
            // Disable product field and add document button
            $('#id_product').prop('disabled', true);
            $('#id_product').select2('enable');  // Keep select2 enabled to show options
            $('#add-document').prop('disabled', true);
        }
    }

    /**
     * Setup customer change event handler
     */
    function setupCustomerChangeHandler() {
        $('#id_customer').change(checkCustomerSelected);
    }

    /**
     * Setup product change event handler to load required/optional documents
     */
    function setupProductChangeHandler() {
        $('#id_product').change(function() {
            var selectedProduct = $(this).val();
            $('#document-form-list').empty(); // Remove all existing required document forms

            if (selectedProduct) {
                loadProductDocuments(selectedProduct);
            }
        });
    }

    /**
     * Load required and optional documents for the selected product
     * @param {string} productId - The ID of the selected product
     */
    function loadProductDocuments(productId) {
        // Build the API URL - replace placeholder with actual product ID
        var url = $('#id_product').data('api-url');
        if (!url) {
            // Fallback: construct URL from template pattern
            var urlPattern = window.productApiUrlPattern || '';
            url = urlPattern.replace('123456', productId);
        }

        restApiCall('GET', url, null,
            function(data) {
                // Get required documents from product
                var requiredDocuments = data.required_documents || [];
                var optionalDocuments = data.optional_documents || [];

                // Create new required document forms
                createDocumentForms(requiredDocuments, 0, true);

                // Create new optional document forms
                createDocumentForms(optionalDocuments, requiredDocuments.length, false);

                // Update total forms count
                var totalForms = requiredDocuments.length + optionalDocuments.length;
                $('#id_documents-TOTAL_FORMS').val(totalForms);
            },
            function(error) {
                console.error('Error loading product documents:', error);
            }
        );
    }

    /**
     * Create document forms from a list of documents
     * @param {Array} documents - Array of document objects
     * @param {number} startIndex - Starting index for form numbering
     * @param {boolean} isRequired - Whether documents are required
     */
    function createDocumentForms(documents, startIndex, isRequired) {
        for (var i = 0; i < documents.length; i++) {
            var formIndex = startIndex + i;
            var newFormHtml = $('#empty-form').html().replace(/__prefix__/g, formIndex);
            var newForm = $(newFormHtml);

            // Set the document type
            newForm.find('select[name=documents-' + formIndex + '-doc_type]').val(documents[i].id);

            // Set required checkbox for optional documents
            if (!isRequired) {
                newForm.find('input[name=documents-' + formIndex + '-required]').prop('checked', false);
            }

            $('#document-form-list').append(newForm);
        }

        // Filter options for all forms after creation
        $('#document-form-list .document_form').each(function(index) {
            filterDocTypeOptions(index);
        });
    }

    /**
     * Setup add document button handler
     */
    function setupAddDocumentHandler() {
        document.getElementById('add-document').addEventListener('click', function() {
            var formIdx = $('#id_documents-TOTAL_FORMS').val();
            var newForm = $('#empty-form').clone().html().replace(/__prefix__/g, formIdx);
            $('#document-form-list').append(newForm);
            $('#id_documents-TOTAL_FORMS').val(parseInt(formIdx) + 1);
            $('#id_documents-' + formIdx + '-step').val(parseInt(formIdx) + 1);

            // Filter the doc_type options to show only remaining documents
            filterDocTypeOptions(formIdx);
        }, false);
    }

    /**
     * Filter doc_type options in the specified form to exclude already selected document types
     * @param {number} formIdx - The index of the form to filter
     */
    function filterDocTypeOptions(formIdx) {
        var selectElement = $('#id_documents-' + formIdx + '-doc_type');
        var selectedDocTypes = getSelectedDocTypes();
        var currentSelected = selectElement.val();

        // Show all options first
        selectElement.find('option').show();

        // Hide options that are already selected in other forms
        selectedDocTypes.forEach(function(docTypeId) {
            if (docTypeId !== currentSelected) {
                selectElement.find('option[value="' + docTypeId + '"]').hide();
            }
        });
    }

    /**
     * Get all currently selected document type IDs from existing forms
     * @returns {Array} Array of selected document type IDs
     */
    function getSelectedDocTypes() {
        var selectedDocTypes = [];
        $('#document-form-list .document_form select[name*="-doc_type"]').each(function() {
            var value = $(this).val();
            if (value && value !== '') {
                selectedDocTypes.push(value);
            }
        });
        return selectedDocTypes;
    }

    /**
     * Setup remove document button handler (delegated event)
     */
    function setupRemoveDocumentHandler() {
        $(document).on('click', '.remove-document-btn', function() {
            if ($('.document_form').length > 1) {
                $(this).parent().remove();
                reindexDocumentForms();
            }
        });
    }

    /**
     * Setup doc_type change handler to update available options in other forms
     */
    function setupDocTypeChangeHandler() {
        $(document).on('change', 'select[name*="-doc_type"]', function() {
            // Re-filter options for all doc_type selects
            $('#document-form-list .document_form').each(function(index) {
                filterDocTypeOptions(index);
            });
        });
    }

    /**
     * Reindex all document forms after removal
     */
    function reindexDocumentForms() {
        var forms = $('#document-form-list .document_form');
        $('#id_documents-TOTAL_FORMS').val(forms.length);

        var i = 0;
        for (var form of forms.toArray()) {
            $(form).find('input,select,checkbox').each(function() {
                var name = $(this).attr('name');
                var id = $(this).attr('id');

                if (name) {
                    $(this).attr('name', name.replace(/-\d+-/, '-' + i + '-'));
                }
                if (id) {
                    $(this).attr('id', id.replace(/-\d+-/, '-' + i + '-'));
                }
            });
            i++;
        }

        // Re-filter doc_type options for all forms after reindexing
        forms.each(function(index) {
            filterDocTypeOptions(index);
        });
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDocApplicationCreate);
    } else {
        initDocApplicationCreate();
    }
})();
