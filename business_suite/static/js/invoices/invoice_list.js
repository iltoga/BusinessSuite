/**
 * @module invoices/invoice_list
 * @description Handles invoice list page interactions including:
 *   - Mark as paid modal payment date initialization
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';

    /**
     * Initialize payment date fields in mark-as-paid modals
     * Sets the payment date to today when modal is opened if not already set
     */
    function initMarkAsPaidModals() {
        // Find all mark-as-paid modals
        const modals = document.querySelectorAll('[id^="markAsPaidModal"]');
        
        modals.forEach(function(modal) {
            modal.addEventListener('shown.bs.modal', function() {
                // Extract invoice ID from modal ID (e.g., "markAsPaidModal123" -> "123")
                const modalId = modal.id.replace('markAsPaidModal', '');
                const paymentDateInput = document.getElementById('payment_date_' + modalId);
                
                // Set to today if field exists and is empty
                if (paymentDateInput && !paymentDateInput.value) {
                    const today = new Date().toISOString().split('T')[0];
                    paymentDateInput.value = today;
                }
            });
        });
    }

    /**
     * Initialize invoice list functionality
     */
    function initInvoiceList() {
        initMarkAsPaidModals();
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initInvoiceList);
    } else {
        initInvoiceList();
    }
})();
