// Invoice create page JS (extracted from invoice_create.html)
(function(){
    'use strict';

    function parseIntOrDefault(v, def){
        var n = parseInt(v);
        return isNaN(n) ? def : n;
    }

    function assignFieldValue(fieldId, value, inputType){
        if (!value || !fieldId) { return; }
        if (typeof window.setFormFieldValue === 'function') {
            window.setFormFieldValue(fieldId, value, inputType);
            return;
        }
        var field = document.getElementById(fieldId);
        if (field) {
            field.value = value;
            field.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    function updateApplicationButtons(container){
        var $customerSelect = $('#id_customer');
        var selectedCustomerId = $customerSelect.val();
        if (selectedCustomerId) {
            $('#invoice-applications-section').show();
            $('#no-customer-message').hide();
        } else {
            $('#invoice-applications-section').hide();
            $('#no-customer-message').show();
        }
    }

    function updateCustomerApplicationDropdowns(applications){
        $("select[name$='-customer_application']").each(function() {
            var $select = $(this);
            var currentVal = $select.val();
            $select.empty();
            $select.append($('<option>', {value: '', text: '---------'}));
            if (applications && applications.length > 0) {
                applications.forEach(function(app){
                    $select.append($('<option>', { value: app.id, text: app.str_field }));
                });
                $('#invoiceapplication-form-list').show();
            } else {
                $('#invoiceapplication-form-list').hide();
            }
            if (currentVal) $select.val(currentVal);
            $select.trigger('change');
        });
        if (!applications || applications.length === 0) {
            $('#invoiceapplication-form-list').hide();
        } else {
            $('#invoiceapplication-form-list').show();
        }
    }

    function init(container){
        var $container = $(container || document);
        var dataElem = $container.find('#invoice-application-form').first();
        var decimals = parseIntOrDefault(dataElem.data('decimals'), 0);
        var customerId = dataElem.data('customer-id') || null;

        updateApplicationButtons();

        $('#id_customer').on('change', function(){
            updateApplicationButtons();
            var selectedCustomerId = $(this).val();
            if (selectedCustomerId) {
                $.ajax({
                    url: '/api/invoices/get_customer_applications/' + selectedCustomerId + '/',
                    method: 'GET',
                    success: function(data){ updateCustomerApplicationDropdowns(data); },
                    error: function(){ updateCustomerApplicationDropdowns([]); }
                });
            } else {
                updateCustomerApplicationDropdowns([]);
            }
        });

        var initialCustomerId = $('#id_customer').val();
        if (initialCustomerId) {
            $.ajax({
                url: '/api/invoices/get_customer_applications/' + initialCustomerId + '/',
                method: 'GET',
                success: function(data){ updateCustomerApplicationDropdowns(data); },
                error: function(){ updateCustomerApplicationDropdowns([]); }
            });
        }

        // Create new application button
        $(document).on('click', '#create-new-application-btn', function(){
            if (customerId) {
                if (typeof openCustomerApplicationQuickCreateModal === 'function') {
                    openCustomerApplicationQuickCreateModal(customerId, dataElem.data('customer-name'));
                } else {
                    alert('Please select a customer first.');
                }
            } else {
                alert('Please select a customer first.');
            }
        });

        // Expose helper for adding a new row
        window.addInvoiceApplicationRow = function(application){
            var $formList = $('#invoiceapplication-form-list');
            $formList.show();
            var $emptyForm = $('#empty-form');
            var totalForms = $('#id_invoice_applications-TOTAL_FORMS');
            var formIdx = parseInt(totalForms.val());
            var newForm = $emptyForm.html().replace(/__prefix__/g, formIdx);
            var $newFormDiv = $('<div class="invoiceapplication_form p-3 mb-4 border rounded"></div>');
            $newFormDiv.html(newForm);
            $formList.append($newFormDiv);
            $newFormDiv.find('select').select2({ theme: 'bootstrap-5', width: '100%' });
            var $appSelect = $newFormDiv.find('select[name$="-customer_application"]');
            var newOption = new Option(application.display_name, application.id, true, true);
            $appSelect.append(newOption).trigger('change');
            var $amountInput = $newFormDiv.find('input[name$="-amount"]');
            $amountInput.val(application.base_price.toFixed(decimals));
            totalForms.val(formIdx + 1);
            $newFormDiv.find('.remove-invoiceapplication-btn').on('click', function(){ $newFormDiv.remove(); });
            $("select[name$='-customer_application']").each(function(){
                var $select = $(this);
                if ($select.val() === "" && $select.find('option').length === 1) {
                    $select.closest('.invoiceapplication_form').hide();
                } else { $select.closest('.invoiceapplication_form').show(); }
            });
        };
    }

    // Auto initialize on page load
    if (document.readyState !== 'loading') {
        init(document);
    } else {
        document.addEventListener('DOMContentLoaded', function(){ init(document); });
    }
})();
