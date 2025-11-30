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
     * Initialize invoice detail page functionality
     */
    function initInvoiceDetail() {
        initMarkAsPaidModal();
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initInvoiceDetail);
    } else {
        initInvoiceDetail();
    }
})();
