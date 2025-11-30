/**
 * Customer Form Module
 * 
 * Handles customer form interactions including:
 * - Customer type toggle (person vs company)
 * - Name capitalization for first and last names
 * - Dynamic field visibility based on customer type
 * 
 * @module customers/customer_form
 * @requires utils.js (capitalizeFirstLetter function)
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';
    
    /**
     * Initializes the customer form functionality
     */
    function initCustomerForm() {
        var firstNameInput = document.getElementById('id_first_name');
        var lastNameInput = document.getElementById('id_last_name');
        var customerTypeInputs = document.querySelectorAll('input[name="customer_type"]');

        /**
         * Toggles the visibility of person-only fields based on customer type
         */
        function togglePersonFields() {
            var checkedInput = document.querySelector('input[name="customer_type"]:checked');
            if (!checkedInput) {
                return;
            }
            
            var customerType = checkedInput.value;
            var personFields = document.querySelectorAll('.person-only-field');
            var personFieldsContainer = document.getElementById('person_fields_container');

            if (customerType === 'company') {
                personFields.forEach(function(field) {
                    field.style.display = 'none';
                });
                if (personFieldsContainer) {
                    personFieldsContainer.style.display = 'none';
                }
            } else {
                personFields.forEach(function(field) {
                    field.style.display = 'block';
                });
                if (personFieldsContainer) {
                    personFieldsContainer.style.display = 'block';
                }
            }
        }

        // Add event listeners to customer type radio buttons
        customerTypeInputs.forEach(function(input) {
            input.addEventListener('change', togglePersonFields);
        });

        // Initialize field visibility on page load
        togglePersonFields();

        // Add capitalization event listeners to name fields
        if (firstNameInput) {
            firstNameInput.addEventListener('change', function(e) {
                firstNameInput.value = capitalizeFirstLetter(firstNameInput.value);
            });
        }

        if (lastNameInput) {
            lastNameInput.addEventListener('change', function(e) {
                lastNameInput.value = capitalizeFirstLetter(lastNameInput.value);
            });
        }
    }
    
    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCustomerForm);
    } else {
        initCustomerForm();
    }
})();
