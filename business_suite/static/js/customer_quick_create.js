/* Customer Quick Create Modal JS
   Moved out of business_suite/templates/modals/customer_quick_create_modal.html
*/
(function() {
    'use strict';
    var $modalSelector = '#customerQuickCreateModal';
    var $formSelector = '#customerQuickCreateForm';
    var $submitBtnSelector = '#customerQuickCreateSubmitBtn';
    var $errorsSelector = '#customerQuickCreateErrors';
    var $customerTypeSelector = '#id_quick_customer_type';

    function init() {
        var $modal = $($modalSelector);
        if (!$modal.length) return;
        var $form = $($formSelector);
        var $submitBtn = $($submitBtnSelector);
        var $errors = $($errorsSelector);
        var $customerType = $($customerTypeSelector);
        var select2Initialized = false;
        var targetSelectId = null;

        function togglePersonFields() {
            var customerType = $customerType.val();
            var $personFields = $('.person-only-field-quick');
            var $personRequired = $('.person-required');
            var $companyRequired = $('.company-required');
            var $firstNameInput = $('#id_quick_first_name');
            var $lastNameInput = $('#id_quick_last_name');
            var $companyNameInput = $('#id_quick_company_name');

            if (customerType === 'company') {
                $personFields.hide();
                $personRequired.hide();
                $companyRequired.show();
                $firstNameInput.prop('required', false);
                $lastNameInput.prop('required', false);
                $companyNameInput.prop('required', true);
            } else {
                $personFields.show();
                $personRequired.show();
                $companyRequired.hide();
                $firstNameInput.prop('required', true);
                $lastNameInput.prop('required', true);
                $companyNameInput.prop('required', false);
            }
        }

        $customerType.on('change', togglePersonFields);

        window.openCustomerQuickCreateModal = function(selectElementId) {
            targetSelectId = selectElementId;
            $form[0].reset();
            $errors.addClass('d-none').html('');

            if (!select2Initialized) {
                $('#id_quick_nationality').select2({
                    theme: 'bootstrap-5',
                    dropdownParent: $modal,
                    placeholder: 'Select nationality',
                    allowClear: false,
                    width: '100%',
                });
                select2Initialized = true;
            }

            $('#id_quick_nationality').val('').trigger('change');
            $customerType.val('person');
            togglePersonFields();
            $modal.modal('show');
            resetPassportImportQuickSection();
        };

        function resetPassportImportQuickSection() {
            var $passportImportQuick = $('#passport-import-quick');
            if ($passportImportQuick.length) {
                $passportImportQuick.find('input[type=file]').val('');
                $passportImportQuick.find('[data-role="passport-import-preview"]').addClass('d-none').attr('src', '');
                $passportImportQuick.find('[data-role="passport-clipboard-preview"]').addClass('d-none').attr('src', '');
                $passportImportQuick.find('[data-role="passport-import-success"]').addClass('d-none');
                $passportImportQuick.find('[data-role="passport-import-error"]').addClass('d-none');
                $passportImportQuick.find('[data-role="passport-clipboard-status"]').html('');
                $passportImportQuick.find('[data-role="use-ai-toggle"]').prop('checked', false);
            }
        }

        $form.on('submit', function(e) {
            e.preventDefault();
            $errors.addClass('d-none').html('');
            $submitBtn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Creating...');

            $.ajax({
                url: $form.data('api-url') || '/api/customers/quick-create/',
                method: 'POST',
                data: $form.serialize(),
                headers: {
                    'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]', $form).val()
                },
                success: function(response) {
                    if (response.success) {
                        if (targetSelectId) {
                            var $targetSelect = $('#' + targetSelectId);
                            var displayName = response.customer.company_name ?
                                response.customer.full_name + ' (' + response.customer.company_name + ')' :
                                response.customer.full_name;
                            var newOption = new Option(displayName, response.customer.id, true, true);
                            $targetSelect.append(newOption).trigger('change');
                        }
                        $modal.modal('hide');
                        $form[0].reset();
                    } else {
                        var errorHtml = '<ul class="mb-0">';
                        $.each(response.errors, function(field, errors) {
                            $.each(errors, function(i, error) { errorHtml += '<li>' + error + '</li>'; });
                        });
                        errorHtml += '</ul>';
                        $errors.html('<strong>An error occurred while creating the customer:</strong> ' + errorHtml).removeClass('d-none');
                    }
                },
                error: function(xhr) {
                    var errorMsg = 'An error occurred while creating the customer.';
                    if (xhr.responseJSON && xhr.responseJSON.error) {
                        errorMsg = xhr.responseJSON.error;
                    }
                    $errors.html(errorMsg).removeClass('d-none');
                },
                complete: function() {
                    $submitBtn.prop('disabled', false).html('<i class="fas fa-save"></i> Create Customer');
                }
            });
        });

        $modal.on('hidden.bs.modal', function() {
            $form[0].reset();
            $errors.addClass('d-none').html('');
            $('#id_quick_nationality').val('').trigger('change');
            $customerType.val('person');
            togglePersonFields();
            targetSelectId = null;
            resetPassportImportQuickSection();
        });
    }

    $(document).ready(function() { init(); });
})();
