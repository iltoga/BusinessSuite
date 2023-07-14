// Use IIFE to avoid polluting the global namespace
(function (currencyDecimalPlaces, customerApplications, maskedUrlNewInvoice, form_action_name, selectedCustomerApplicationPk) {
    var allSelected = false;

    $(document).ready(function () {
        checkSelected();
        if (form_action_name == 'update') {
            // disable the customer dropdown when updating an invoice
            $('[name^=invoice_applications-][name$=-customer_application]').each(function () {
                $(this).prop('disabled', true);
            });
        }
        if (form_action_name == 'create') {
            // hide "delete" checkbox for new forms
            $('[name^=invoice_applications-][name$=-DELETE]').each(function () {
                $(this).parent().hide();
            });
            // if selectedCustomerApplicationPk is set, select the dropdown with name invoice_applications-0-customer_application
            if (selectedCustomerApplicationPk != "") {
                // FIXME: since 'customer' dropdown is a select2 dropdown, if we disable it, the value is not sent when the form is submitted
                // even if we add a hidden input with the same name and value. For now we just leave it enabled.
                // setDropdownReadonly('customer');
                setDropdownReadonly('invoice_applications-0-customer_application');
                // update the price field
                var dueAmount = customerApplications.find(function (application) {
                    return application.pk == selectedCustomerApplicationPk;
                }).fields.product.base_price;
                // sanitize the value given currencyDecimalPlaces
                dueAmount = roundToCurrencyDecimalPlaces(dueAmount, currencyDecimalPlaces)
                $('[name=invoice_applications-0-amount]').val(dueAmount);
                updateTotalAmount();
                updateCustomerApplicationSelections();
            }
        }
        updateCustomerApplicationSelections();
    });


    $(document).on('submit', '#invoice-application-form', function (event) {
        event.preventDefault();
        var form = $(this);
        form.find('select').prop('disabled', false);
        addHiddenFieldsForDisabledElements(form);
        form[0].submit(); // Use DOM submit function instead of jQuery submit
    });


    $(document).on('change', "select[name$='-customer_application']", function () {
        var selected = $(this).val();

        var id = $(this).attr('id');
        var dueAmountId = id.replace('customer_application', 'amount');
        var dueAmountInput = $('#' + dueAmountId);
        if (selected && customerApplications) {
            var application = customerApplications.find(function (application) {
                return application.pk == selected;
            });
            if (application) {
                var dueAmount = application.fields.product.base_price;
                // sanitize the value given currencyDecimalPlaces
                dueAmount = roundToCurrencyDecimalPlaces(dueAmount, currencyDecimalPlaces);
                dueAmountInput.val(dueAmount);
            }
        } else {
            dueAmountInput.val('');
        }
        updateTotalAmount();
        updateCustomerApplicationSelections();
    });


    $(document).on('change', "input[name$='-amount']", function () {
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
        if (allSelected) {
            return;
        }
        var formIdx = $('#id_invoice_applications-TOTAL_FORMS').val();
        var newForm = $('#empty-form').clone().html().replace(/__prefix__/g, formIdx);
        $('#invoiceapplication-form-list').append(newForm);
        $('#id_invoice_applications-TOTAL_FORMS').val(parseInt(formIdx) + 1);
        $('#id_invoice_applications-' + formIdx + '-step').val(parseInt(formIdx) + 1);
        $('#id_invoice_applications-' + formIdx + '-DELETE').parent().hide();
        if (form_action_name == 'update') {
            $('[name^=invoice_applications-' + formIdx + '-customer_application]').prop('disabled', false);
            $('[name^=invoice_applications-' + formIdx + '-amount]').prop('disabled', false);
        }
        updateCustomerApplicationSelections();
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
            updateCustomerApplicationSelections();
        }
    });

    function checkSelected() {
        customerVal = $('#id_customer').val();
        if (customerVal && !allSelected) {
            $('#add-invoiceapplication').prop('disabled', false);
        } else {
            $('#add-invoiceapplication').prop('disabled', true);
        }
    }

    function updateTotalAmount() {
        var total = 0.0;
        $('[id$=-amount]').each(function () {
            // unmaks the value and parse it as a float
            total += parseFloat($(this).val().replace(/,/g, '')) || 0;
        });
        $('#id_total_amount').val(total);
    }

    // Set the dropdown to readonly
    // This is used when the invoice is created from a customer application
    // The dropdown must be disabled but still send the value when the form is submitted
    function setDropdownReadonly(field_name) {
        if (field_name == undefined) {
            return;
        }
        var $select = $('[name="' + field_name + '"]');
        $select.val(selectedCustomerApplicationPk);
        $select.prop('disabled', true);

        // Add a corresponding hidden input (this is to make sure the value is sent when the form is submitted)
        var $hiddenInput = $('<input>').attr({
            type: 'hidden',
            name: $select.attr('name'),
            value: $select.val()
        });
        $select.after($hiddenInput);
    }

    // Update the customer application dropdowns
    // Disable the selected value in all other dropdowns
    // Update the customer application dropdowns
    // Disable the selected value in all other dropdowns
    function updateCustomerApplicationSelections() {
        // // Find all the customer application select boxes
        // var $selects = $("select[name$='-customer_application']");

        // // Keep track of all selected options
        // var selectedOptions = new Set();

        // $selects.each(function () {
        //     // Enable all options for this select
        //     $(this).find('option').prop('disabled', false);
        // });

        // // First, mark all selected options
        // $selects.each(function () {
        //     var selectedVal = $(this).val();
        //     // Skip if no value selected or if placeholder selected
        //     if (!selectedVal || selectedVal == "") {
        //         return;
        //     }
        //     selectedOptions.add(selectedVal);
        // });

        // // Then, disable selected options in all select boxes and check if there are any options left
        // var availableOptions = new Set();
        // $selects.each(function () {
        //     var $select = $(this);
        //     $select.find('option').each(function () {
        //         var optionVal = $(this).val();
        //         if (selectedOptions.has(optionVal)) {
        //             // This option is selected in another select box, disable it
        //             $(this).prop('disabled', true);
        //         } else if (optionVal != "") {
        //             // This option is available, add it to the set of available options
        //             availableOptions.add(optionVal);
        //         }
        //     });
        // });

        // // Disable the "add invoice application" button if there are no available options left
        // $('#add-invoiceapplication').prop('disabled', availableOptions.size === 0);
    }

    function addHiddenFieldsForDisabledElements(formset) {
        var promises = [];

        formset.each(function () {
            var form = $(this);

            // For non-select fields
            form.find(':disabled[name]').each(function () {
                var disabledElement = $(this);
                var promise = new Promise(function (resolve) {
                    form.append(
                        $('<input>', {
                            type: 'hidden',
                            name: disabledElement.attr('name'),
                            value: disabledElement.val()
                        })
                    );
                    resolve();
                });
                promises.push(promise);
            });

            // For select fields
            form.find('select option:selected').each(function () {
                var selectedOption = $(this);
                var promise = new Promise(function (resolve) {
                    form.append(
                        $('<input>', {
                            type: 'hidden',
                            name: selectedOption.parent().attr('name'),
                            value: selectedOption.val()
                        })
                    );
                    resolve();
                });
                promises.push(promise);
            });
        });

        // Return a promise that resolves when all the promises in the array are resolved
        return Promise.all(promises);
    }


    function resetForms() {
        $('#invoiceapplication-form-list').empty();
        $('#id_invoice_applications-TOTAL_FORMS').val(0);
        updateTotalAmount();
    }

})(decimals, customerApplications, masked_url, form_action_name, selectedCustomerApplicationPk);