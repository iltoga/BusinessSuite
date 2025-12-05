/* Surah Permohonan page JS: extracted from surat_permohonan.html inline block
   Purpose: initialize select2, handle customer selection, new customer modal, and AJAX form submit with blob download
*/
(function(){
    'use strict';

    function showToast(message, type) {
        var $container = $('#toast-container');
        if (!$container.length) {
            $container = $('<div id="toast-container" aria-live="polite" aria-atomic="true" class="position-fixed top-0 end-0 p-3" style="z-index: 1080;"></div>');
            $('body').append($container);
        }
        var toastId = 'toast-' + Date.now();
        var toastHtml = `
            <div id="${toastId}" class="toast align-items-center text-bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="d-flex">
                    <div class="toast-body">${message}</div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            </div>`;
        var $toast = $(toastHtml);
        $container.append($toast);
        var bsToast = new bootstrap.Toast(document.getElementById(toastId), { delay: 5000 });
        bsToast.show();
    }

    function init(container) {
        var $container = $(container || document);
        var $form = $container.find('#surat-permohonan-form');
        if (!$form.length) return;

        // Initialize Select2 for customer dropdown - no clear button
        var $customerSelect = $form.find('#id_customer');
        if ($customerSelect.length && $.fn.select2) {
            $customerSelect.select2({ theme: 'bootstrap-5', width: '100%', placeholder: 'Select a customer...', allowClear: false });
        }

        // Initialize select2 for country dropdown (shows names from CountryCode.country_idn)
        var $countrySelect = $form.find('#id_country');
        if ($countrySelect.length && $.fn.select2) {
            $countrySelect.select2({ theme: 'bootstrap-5', width: '100%', placeholder: 'Select nationality...' });
        }

        // Add form-control class to clamped inputs within the form only
        $form.find('input, textarea').addClass('form-control');

        // Initialize hidden customer field if pre-selected and trigger change
        var $hiddenCustomer = $form.find('#id_customer_selected');
        var initCustomer = $customerSelect.val();
        if (initCustomer && $hiddenCustomer.length) {
            $hiddenCustomer.val(initCustomer);
            $customerSelect.trigger('change');
        }

        // Customer selection change (namespaced to avoid duplicate bindings)
        // Add a short debounce to avoid multiple rapid calls
        var _changeTimeout = null;
        $customerSelect.off('change.surat').on('change.surat', function() {
            var customerId = $(this).val();
            if (_changeTimeout) clearTimeout(_changeTimeout);
            _changeTimeout = setTimeout(function() {
            if (customerId) {
                if ($hiddenCustomer.length) $hiddenCustomer.val(customerId);
                $.ajax({
                    url: '/api/customers/' + customerId + '/',
                    method: 'GET',
                    success: function(customer) {
                        $form.find('#id_name').val(customer.full_name || '');
                        // gender comes pre-formatted from API using Customer.get_gender_display with default language
                        $form.find('#id_gender').val(customer.gender_display || '');
                        $form.find('#id_country').val(customer.nationality_code || customer.nationality_name || '');
                        // If select2 is used, trigger change to update display
                        var $countrySelect = $form.find('#id_country');
                        if ($countrySelect.length && $countrySelect.data('select2')) {
                            $countrySelect.trigger('change');
                        }
                        $form.find('#id_birth_place').val(customer.birth_place || '');
                        $form.find('#id_birthdate').val(customer.birthdate || '');
                        $form.find('#id_passport_no').val(customer.passport_number || '');
                        $form.find('#id_passport_exp_date').val(customer.passport_expiration_date || '');
                        $form.find('#id_address_bali').val(customer.address_bali || '');
                    },
                    error: function() {
                        showToast('Could not fetch customer details. Please try again.', 'danger');
                    }
                });
            } else {
                $form.find('#id_name, #id_gender, #id_country, #id_birth_place, #id_birthdate, #id_passport_no, #id_passport_exp_date, #id_address_bali').val('');
                if ($hiddenCustomer.length) $hiddenCustomer.val('');
            }
            _changeTimeout = null;
            }, 150);
        });

        // Handle add customer button
        $form.find('#add-customer-btn').off('click.surat').on('click.surat', function() {
            if (typeof openCustomerQuickCreateModal === 'function') {
                openCustomerQuickCreateModal('id_customer');
            } else {
                showToast('Create customer modal not available', 'warning');
            }
        });

        // Handle form submit via AJAX to download file (namespaced to avoid duplicates)
        $form.off('submit.surat').on('submit.surat', function(e) {
            // Prevent double-submission: set a flag while processing
            if ($form.data('surat-in-progress')) return;
            $form.data('surat-in-progress', true);
            e.preventDefault();
            var formEl = this;
            var url = $form.attr('action');
            var formData = new FormData(formEl);
            $.ajax({
                url: url,
                method: 'POST',
                data: formData,
                processData: false,
                contentType: false,
                xhrFields: { responseType: 'blob' },
                success: function(data, status, xhr) {
                    var filename = 'surat_permohonan.docx';
                    var disposition = xhr.getResponseHeader('Content-Disposition');
                    if (disposition && disposition.indexOf('filename=') !== -1) {
                        var match = disposition.match(/filename\*=UTF-8''([^;]+)|filename="?([^;"']+)"?/i);
                        if (match) filename = decodeURIComponent(match[1] || match[2]);
                    }
                    var blob = new Blob([data], { type: xhr.getResponseHeader('Content-Type') || 'application/octet-stream' });
                    var link = document.createElement('a');
                    link.href = window.URL.createObjectURL(blob);
                    link.download = filename;
                    document.body.appendChild(link);
                    link.click();
                    setTimeout(function() { window.URL.revokeObjectURL(link.href); link.remove(); }, 1000);
                },
                error: function(xhr) {
                    var msg = 'An error occurred';
                    try {
                        var txt = xhr.responseText;
                        try {
                            var json = JSON.parse(txt);
                            if (json && json.error) msg = json.error;
                            else if (json && json.errors) msg = JSON.stringify(json.errors);
                        } catch (e) { msg = txt || msg; }
                    } catch (e) { msg = xhr.statusText || msg; }
                    showToast(msg, 'danger');
                },
                complete: function() {
                    // Reset in-progress flag on completion
                    $form.data('surat-in-progress', false);
                }
            });
        });
    }

    if (document.readyState !== 'loading') init(document);
    else document.addEventListener('DOMContentLoaded', function(){ init(document); });
})();
