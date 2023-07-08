// Use IIFE to avoid polluting the global namespace
(function (currencyDecimalPlaces, customerApplications, maskedUrlNewInvoice) {
    console.log('invoice_create.js loaded');
    console.log('customerApplications: ', customerApplications);

    $(document).ready(function () {
        checkSelected();
    });

    $(document).on('change', "select[name$='-customer_application']", function () {
        var selected = $(this).val();
        var id = $(this).attr('id');
        var dueAmountId = id.replace('customer_application', 'due_amount');
        var dueAmountInput = $('#' + dueAmountId);
        if (selected && customerApplications) {
            var dueAmount = customerApplications.find(function (application) {
                return application.pk == selected;
            }).fields.price;
            dueAmountInput.val(dueAmount);
        } else {
            dueAmountInput.val('');
        }
    });

    $(document).on('change', "input[name$='-due_amount']", function () {
        updateTotalAmount();
    });

    // On customer's drowpdown change, reload the page posting the customer id as query parameter
    $('#id_customer').change(function () {
        var selection = $(this).val();
        if (selection) {
            url = maskedUrlNewInvoice.replace('123456', selection);
            window.location.href = url;
        }
    });

    document.getElementById('add-invoiceapplication').addEventListener('click', function () {
        var formIdx = $('#id_invoice_applications-TOTAL_FORMS').val();
        var newForm = $('#empty-form').clone().html().replace(/__prefix__/g, formIdx);
        $('#invoiceapplication-form-list').append(newForm);
        $('#id_invoice_applications-TOTAL_FORMS').val(parseInt(formIdx) + 1);
        $('#id_invoice_applications-' + formIdx + '-step').val(parseInt(formIdx) + 1);
        $('#id_invoice_applications-' + formIdx + '-DELETE').parent().hide();
    });

    $(document).on('click', '.remove-invoiceapplication-btn', function () {
        if ($('.invoiceapplication_form').length > 1) {
            $(this).parent().remove();
            var forms = $('#invoiceapplication-form-list .invoiceapplication_form'); // Get all the forms
            $('#id_invoice_applications-TOTAL_FORMS').val(forms.length); // Update the total number of forms
            var i = 0;
            // Go through the forms and set their indices, names and IDs
            for (form of forms.toArray()) {
                $(form).find('input,select,checkbox').each(function () {
                    $(this).attr('name', $(this).attr('name').replace(/-\d+-/, '-' + i + '-'));
                    $(this).attr('id', $(this).attr('id').replace(/-\d+-/, '-' + i + '-'));
                });
                i++;
            }
            updateTotalAmount();
        }
    });

    function checkSelected() {
        customerVal = $('#id_customer').val();
        if (customerVal) {
            $('#add-invoiceapplication').prop('disabled', false);

        } else {
            $('#add-invoiceapplication').prop('disabled', true);
        }
    }

    function resetForms() {
        $('#invoiceapplication-form-list').empty();
        $('#id_invoice_applications-TOTAL_FORMS').val(0);
        updateTotalAmount();
    }

    function updateTotalAmount() {
        var total = 0.0;
        $('[id$=-due_amount]').each(function () {
            // unmaks the value and parse it as a float
            total += parseFloat($(this).val().replace(/,/g, '')) || 0;
        });
        $('#id_total_amount').val(total);
    }

})(decimals, customerApplications, masked_url);