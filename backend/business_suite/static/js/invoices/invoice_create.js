// Invoice create page JS (extracted from invoice_create.html)
(function(){
    'use strict';

    // Module-level variables for customer tracking
    var customerId = null;
    var customerName = '';
    var decimals = 0;

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
            // Update customerId and customerName when customer changes
            customerId = selectedCustomerId;
            customerName = $customerSelect.find('option:selected').text();
            $('#invoice-applications-section').show();
            $('#no-customer-message').hide();
        } else {
            customerId = null;
            customerName = '';
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
                    var appId = app.id || app.pk || (app.fields && app.fields.pk) || '';
                    var appText = '';
                    if (app.str_field) {
                        appText = app.str_field;
                    } else if (app.fields && app.fields.product) {
                        var prod = app.fields.product;
                        var cust = app.fields.customer;
                        if (prod && prod.code && prod.name && cust && cust.full_name) {
                            appText = prod.code + ' - ' + prod.name + ' (' + cust.full_name + ')';
                        } else if (prod && prod.code && prod.name) {
                            appText = prod.code + ' - ' + prod.name;
                        } else if (app.fields && app.fields.doc_date) {
                            appText = 'Application ' + appId + ' (' + app.fields.doc_date + ')';
                        } else {
                            appText = 'Application ' + appId;
                        }
                    } else {
                        appText = app.display_name || appText || 'Application ' + appId;
                    }
                    $select.append($('<option>', { value: appId, text: appText }));
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

    function setCustomerApplicationsFromApi(applications) {
        // Convert API serializer format to Django serialized format expected by invoice_form.js
        if (typeof applications === 'undefined' || applications === null) {
            window.customerApplications = [];
            return;
        }
        window.customerApplications = applications.map(function(app) {
            return {
                pk: app.id,
                fields: {
                    product: app.product || {},
                    customer: app.customer || {},
                    doc_date: app.doc_date || null
                }
            };
        });
    }

    function init(container){
        var $container = $(container || document);
        var dataElem = $container.find('#invoice-application-form').first();
        // Initialize module-level variables (no var - use module scope)
        decimals = parseIntOrDefault(dataElem.data('decimals'), 0);
        customerId = dataElem.data('customer-id') || null;
        customerName = dataElem.data('customer-name') || '';

        updateApplicationButtons();

        $('#id_customer').on('change', function(){
            updateApplicationButtons();
            var selectedCustomerId = $(this).val();
            if (selectedCustomerId) {
                $.ajax({
                    url: '/api/invoices/get_customer_applications/' + selectedCustomerId + '/',
                    method: 'GET',
                        success: function(data){ setCustomerApplicationsFromApi(data); if (typeof window.setInvoiceFormCustomerApplications === 'function') { window.setInvoiceFormCustomerApplications(window.customerApplications); } updateCustomerApplicationDropdowns(data); },
                    error: function(){ setCustomerApplicationsFromApi([]); updateCustomerApplicationDropdowns([]); }
                });
            } else {
                setCustomerApplicationsFromApi([]);
                updateCustomerApplicationDropdowns([]);
            }
        });

        var initialCustomerId = $('#id_customer').val();
        if (initialCustomerId) {
            $.ajax({
                url: '/api/invoices/get_customer_applications/' + initialCustomerId + '/',
                method: 'GET',
                    success: function(data){ setCustomerApplicationsFromApi(data); if (typeof window.setInvoiceFormCustomerApplications === 'function') { window.setInvoiceFormCustomerApplications(window.customerApplications); } updateCustomerApplicationDropdowns(data); },
                error: function(){ setCustomerApplicationsFromApi([]); updateCustomerApplicationDropdowns([]); }
            });
        }

        // Create new application button
        $(document).on('click', '#create-new-application-btn', function(){
            if (customerId) {
                if (typeof openCustomerApplicationQuickCreateModal === 'function') {
                    openCustomerApplicationQuickCreateModal(customerId, customerName);
                } else {
                    alert('Quick create modal not available.');
                }
            } else {
                alert('Please select a customer first.');
            }
        });

        // Expose helper for adding a new row
        window.addInvoiceApplicationRow = function(application){
            // Add the application to the global customerApplications array used by invoice_form.js
            if (typeof window.customerApplications === 'undefined') {
                window.customerApplications = [];
            }
            window.customerApplications.push({
                pk: application.id,
                fields: {
                    product: {
                        base_price: application.base_price,
                        retail_price: application.retail_price,
                        name: application.product_name || application.product_name || '',
                        code: application.product_code || ''
                    },
                    customer: { full_name: application.customer_name || (dataElem ? dataElem.data('customer-name') : '') },
                    doc_date: application.doc_date || null
                }
            });
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
            var initialAmount = application.retail_price;
            if (initialAmount === undefined || initialAmount === null) {
                initialAmount = application.base_price;
            }
            $amountInput.val(Number(initialAmount || 0).toFixed(decimals));
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
