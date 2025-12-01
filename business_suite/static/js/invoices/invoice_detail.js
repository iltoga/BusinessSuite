/**
 * @module invoices/invoice_detail
 * @description Handles invoice detail page interactions including:
 *   - Payment date initialization in mark as paid modal
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';

    /**
     * Initialize the mark as paid modal
     * Ensures payment date is set to today when modal opens
     */
    function initMarkAsPaidModal() {
        var markAsPaidModal = document.getElementById('markAsPaidModal');
        if (markAsPaidModal) {
            markAsPaidModal.addEventListener('shown.bs.modal', function() {
                var paymentDateInput = document.getElementById('payment_date');
                if (paymentDateInput && !paymentDateInput.value) {
                    var today = new Date().toISOString().split('T')[0];
                    paymentDateInput.value = today;
                }
            });
        }
    }

    /**
     * Initialize the delete invoice modal
     * Adds confirmation dialog before submitting delete form
     */
    function initDeleteInvoiceModal() {
        var deleteForm = document.getElementById('deleteInvoiceForm');
        if (deleteForm) {
            deleteForm.addEventListener('submit', function(e) {
                var forceDeleteCheckbox = document.getElementById('force_delete_confirmed');
                if (!forceDeleteCheckbox || !forceDeleteCheckbox.checked) {
                    e.preventDefault();
                    alert('Please confirm the force delete action by checking the checkbox.');
                    return false;
                }
                
                var confirmed = confirm('Are you ABSOLUTELY SURE you want to force delete this invoice and all related data? This action is PERMANENT and cannot be undone!');
                if (!confirmed) {
                    e.preventDefault();
                    return false;
                }
            });
        }
    }

    /**
     * Initialize invoice detail page functionality
     */
    function initInvoiceDetail() {
        initMarkAsPaidModal();
        initDeleteInvoiceModal();
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initInvoiceDetail);
    } else {
        initInvoiceDetail();
    }
})();
