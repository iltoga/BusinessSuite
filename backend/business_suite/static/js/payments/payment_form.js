/**
 * @module payments/payment_form
 * @description Handles payment form interactions including:
 *   - Invoice application selection
 *   - Automatic due amount fetching via AJAX
 *   - Amount field population
 *   - Due amount display formatting
 * @requires utils.js
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';
    
    /**
     * Initializes the payment form functionality
     */
    function initPaymentForm() {
        const invoiceAppSelect = document.querySelector('#id_invoice_application');
        const amountInput = document.querySelector('#id_amount');
        const dueAmountDisplay = document.querySelector('#due-amount-display');
        const dueAmountValue = document.querySelector('#due-amount-value');

        if (!invoiceAppSelect || !amountInput) {
            return; // Elements not found, exit early
        }

        // Handle invoice application selection change
        invoiceAppSelect.addEventListener('change', function() {
            const selectedId = this.value;
            
            if (selectedId) {
                fetchDueAmount(selectedId, amountInput, dueAmountDisplay, dueAmountValue);
            } else {
                // Clear amount and hide display when no invoice selected
                amountInput.value = '';
                if (dueAmountDisplay && dueAmountValue) {
                    dueAmountDisplay.style.display = 'none';
                }
            }
        });
    }

    /**
     * Fetches the due amount for a selected invoice application
     * @param {string} invoiceAppId - The ID of the selected invoice application
     * @param {HTMLElement} amountInput - The amount input field element
     * @param {HTMLElement} dueAmountDisplay - The due amount display container element
     * @param {HTMLElement} dueAmountValue - The due amount value span element
     */
    function fetchDueAmount(invoiceAppId, amountInput, dueAmountDisplay, dueAmountValue) {
        const csrftoken = getCsrfToken();

        fetch(`/api/invoices/get_invoice_application_due_amount/${invoiceAppId}/`, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrftoken
            },
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.due_amount !== undefined) {
                // Set the amount input value
                amountInput.value = data.due_amount;
                
                // Format and display the due amount
                if (dueAmountValue) {
                    dueAmountValue.textContent = formatCurrencyValue(data.due_amount);
                    dueAmountDisplay.style.display = 'block';
                }
            }
        })
        .catch(error => {
            console.error('Error fetching due amount:', error);
            alert('Failed to fetch invoice amount. Please try again.');
        });
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPaymentForm);
    } else {
        initPaymentForm();
    }
})();
