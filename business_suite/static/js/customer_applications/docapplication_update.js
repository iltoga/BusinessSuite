/**
 * @module customer_applications/docapplication_update
 * @description Handles document application update form interactions including:
 *   - Dynamic document form management (add/remove) for NEW documents only
 *   - Form validation and field enabling/disabling
 *   - Document type filtering to prevent duplicates
 * @requires jQuery
 * @requires select2
 * @requires utils.js (restApiCall)
 */

(function() {
    'use strict';

    /**
     * Initialize the document application update form
     */
    function initDocApplicationUpdate() {
        setupAddDocumentHandler();
        setupRemoveDocumentHandler();
        setupDocTypeChangeHandler();
        // Initial filter on page load
        filterAllDocTypeForms();
    }

    /**
     * Setup add document button handler
     */
    function setupAddDocumentHandler() {
        document.getElementById('add-document').addEventListener('click', function() {
            var formIdx = $('#id_new_documents-TOTAL_FORMS').val();
            var newForm = $('#empty-form').clone().html().replace(/__prefix__/g, formIdx);
            $('#new-document-form-list').append(newForm);
            $('#id_new_documents-TOTAL_FORMS').val(parseInt(formIdx) + 1);

            // Filter the doc_type options to show only remaining documents
            filterDocTypeOptions(formIdx);
        }, false);
    }

    /**
     * Filter doc_type options in the specified form to exclude already selected document types
     * @param {number} formIdx - The index of the form to filter
     */
    function filterDocTypeOptions(formIdx) {
        var selectElement = $('#id_new_documents-' + formIdx + '-doc_type');
        var selectedDocTypes = getSelectedDocTypes();
        var currentSelected = selectElement.val();

        // Show all options first
        selectElement.find('option').show();

        // Hide options that are already selected in other forms (including existing documents)
        selectedDocTypes.forEach(function(docTypeId) {
            if (docTypeId !== currentSelected) {
                selectElement.find('option[value="' + docTypeId + '"]').hide();
            }
        });
    }

    /**
     * Filter all doc_type forms on initial page load
     */
    function filterAllDocTypeForms() {
        $('#new-document-form-list .new_document_form').each(function(index) {
            filterDocTypeOptions(index);
        });
    }

    /**
     * Get all currently selected document type IDs from both existing and new document forms
     * @returns {Array} Array of selected document type IDs
     */
    function getSelectedDocTypes() {
        var selectedDocTypes = [];

        // Get doc types from existing documents (passed from server)
        if (window.existingDocTypeIds && window.existingDocTypeIds.length > 0) {
            window.existingDocTypeIds.forEach(function(docTypeId) {
                selectedDocTypes.push(String(docTypeId));
            });
        }

        // Get doc types from new documents being added
        $('#new-document-form-list .new_document_form select[name*="-doc_type"]').each(function() {
            var value = $(this).val();
            // Skip if this form is marked for deletion
            var deleteCheckbox = $(this).closest('.new_document_form').find('input[name*="-DELETE"]');
            if (deleteCheckbox.is(':checked')) {
                return; // Skip this iteration
            }
            if (value && value !== '') {
                selectedDocTypes.push(value);
            }
        });

        return selectedDocTypes;
    }

    /**
     * Setup remove document button handler (delegated event)
     * Only for new documents (not yet saved)
     */
    function setupRemoveDocumentHandler() {
        $(document).on('click', '.remove-document-btn', function() {
            var documentForm = $(this).closest('.new_document_form');

            // Just remove the form - these are new documents not yet saved
            if ($('.new_document_form').length > 0) {
                documentForm.remove();
                reindexDocumentForms();
            }
        });
    }

    /**
     * Setup doc_type change handler to update available options in other forms
     */
    function setupDocTypeChangeHandler() {
        $(document).on('change', 'select[name*="-doc_type"]', function() {
            // Re-filter options for all new doc_type selects
            filterAllDocTypeForms();
        });
    }

    /**
     * Reindex all new document forms after removal
     */
    function reindexDocumentForms() {
        var forms = $('#new-document-form-list .new_document_form');
        $('#id_new_documents-TOTAL_FORMS').val(forms.length);

        var i = 0;
        for (var form of forms.toArray()) {
            $(form).find('input,select,checkbox,textarea').each(function() {
                var name = $(this).attr('name');
                var id = $(this).attr('id');

                if (name) {
                    $(this).attr('name', name.replace(/new_documents-\d+-/, 'new_documents-' + i + '-'));
                }
                if (id) {
                    $(this).attr('id', id.replace(/new_documents-\d+-/, 'new_documents-' + i + '-'));
                }
            });
            i++;
        }

        // Re-filter doc_type options for all forms after reindexing
        filterAllDocTypeForms();
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDocApplicationUpdate);
    } else {
        initDocApplicationUpdate();
    }
})();
