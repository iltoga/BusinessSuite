/**
 * Common Utility Functions Module
 * 
 * This module provides reusable utility functions for the Business Suite application.
 * Functions include:
 * - CSRF token handling
 * - REST API calls with automatic CSRF token injection
 * - Currency formatting and parsing
 * - Date format conversion
 * - Form field value setting
 * - String manipulation (capitalization)
 * - Message display (success/error alerts)
 * - AJAX error handling
 * 
 * @module utils
 */

/**
 * Retrieves a cookie value by name
 * @param {string} name - The name of the cookie to retrieve
 * @returns {string|null} The cookie value or null if not found
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        let cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            let cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

/**
 * Retrieves the CSRF token from cookies
 * @returns {string|null} The CSRF token or null if not found
 */
function getCsrfToken() {
    return getCookie('csrftoken');
}

/**
 * Makes a REST API call with automatic CSRF token handling
 * @param {string} method - HTTP method (GET, POST, PUT, DELETE, etc.)
 * @param {string} url - The URL to call
 * @param {Object|FormData} data - The data to send (JSON object or FormData)
 * @param {Function} successCallback - Callback function on success
 * @param {Function} errorCallback - Callback function on error
 */
function restApiCall(method, url, data, successCallback, errorCallback) {

    // Configure the fetch options
    let options = {
        method: method,
        credentials: 'same-origin'
    };

    // If the method is not GET, include the CSRF token and set the body
    if (method.toUpperCase() !== 'GET') {
        let csrftoken = getCsrfToken();
        options.headers = {
            'X-CSRFToken': csrftoken
        };

        // if the data is an instance of FormData, we should not set the Content-Type header
        // the browser will automatically set this to multipart/form-data and include the necessary boundary parameter
        if (data instanceof FormData) {
            // options.headers['Content-Type'] = 'multipart/form-data';
            options.body = data;
        } else {
            options.body = JSON.stringify(data);
            options.headers['Content-Type'] = 'application/json';
        }
    }

    // Perform the fetch
    fetch(url, options)
        .then(async response => {
            if (!response.ok) {
                // Read the response to get the error message
                // Assume server sends { "error": "Error details" } in the response body
                const jsonResponse = await response.json();
                if (jsonResponse.error === undefined || jsonResponse.error === null || jsonResponse.error === '') {
                    jsonResponse.error = response.statusText;
                }
                switch (response.status) {
                    case 403:
                        jsonResponse.error = 'You do not have permission to perform this action';
                        break;
                    case 404:
                        jsonResponse.error = 'The requested resource was not found';
                        break;
                    case 500:
                        jsonResponse.error = 'An internal server error occurred';
                        break;
                }
                throw Error(jsonResponse.error);
            }
            return response.json();
        })
        .then(data => {
            if (successCallback) {
                successCallback(data);
            }
        })
        .catch((error) => {
            if (errorCallback) {
                errorCallback(error);
            }
        });

}

/**
 * Toggles the display of success and error messages
 * @param {boolean} success - Whether the operation was successful
 * @param {string} message - The message to display
 * @param {string} errorElementId - The ID of the error message element
 * @param {string} successElementId - The ID of the success message element
 */
function toggleMessageDisplay(success, message, errorElementId, successElementId) {
    var errorElement = document.getElementById(errorElementId);
    var successElement = document.getElementById(successElementId);

    if (success) {
        errorElement.style.display = 'none';
        successElement.innerHTML = message;
        successElement.style.display = 'block';
    } else {
        successElement.style.display = 'none';
        errorElement.innerHTML = message;
        errorElement.style.display = 'block';
    }
}

/**
 * Toggles the display of a loading spinner and button state
 * @param {boolean} show - Whether to show the spinner
 * @param {string} buttonId - The ID of the button element
 * @param {string} spinnerId - The ID of the spinner element
 */
function toggleSpinnerDisplay(show, buttonId, spinnerId) {
    var button = document.getElementById(buttonId);
    var spinner = document.getElementById(spinnerId);

    if (show) {
        button.disabled = true;
        spinner.style.display = 'inline-block';
    } else {
        button.disabled = false;
        spinner.style.display = 'none';
    }
}

/**
 * Sets the value of a form field based on the field type
 * Handles various input types including text, number, date, select2, etc.
 * @param {string} fieldId - The ID of the form field
 * @param {*} value - The value to set
 * @param {string|null} type - Optional field type override (useful for hidden fields)
 */
function setFormFieldValue(fieldId, value, type = null) {
    var field = document.getElementById(fieldId);
    type = type || field.type;

    // Handle undefined field
    if (!field) {
        console.error(`Field with ID ${fieldId} does not exist`);
        return;
    }

    switch (type) {
        case 'text':
        case 'textarea':
        case 'password':
        case 'email':
        case 'hidden':
        case 'search':
        case 'tel':
        case 'url':
        case 'file':
        case 'range':
        case 'color':
            field.value = value;
            break;

        case 'number':
            field.value = Number(value);
            break;

        case 'date':
        case 'datetime':
        case 'datetime-local':
            var date = new Date(value);
            field.value = date.toISOString().split('T')[0];
            break;

        // passport date format is: yymmdd (example: 201231)
        case 'passport_date':
            field.value = convertDateFormat(value);
            break;

        case 'month':
            var date = new Date(value);
            field.value = date.toISOString().substring(0, 7); // YYYY-MM
            break;

        case 'week':
            var date = new Date(value);
            var week = getWeekNumber(date);
            field.value = date.getFullYear() + '-W' + (week < 10 ? '0' : '') + week; // YYYY-WWW
            break;

        case 'time':
            var date = new Date(value);
            field.value = date.toTimeString().split(' ')[0]; // HH:mm:ss
            break;

        case 'radio':
        case 'checkbox':
            field.checked = Boolean(value);
            break;

        case 'select-one':
        case 'select-multiple':
            var fieldJq = $(field);
            if (fieldJq.hasClass('select2-hidden-accessible')) {
                // It is a select2 element
                fieldJq.val(value).trigger('change');
            } else {
                // It is a regular select element
                field.value = value;
            }
            break;

        default:
            console.error(`Unsupported field type: ${field.type}`);
            break;
    }
}

/**
 * Gets the ISO week number for a given date
 * @param {Date} d - The date object
 * @returns {number} The week number
 */
function getWeekNumber(d) {
    d = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
    var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    var weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return weekNo;
}

/**
 * Converts date format from yymmdd to yyyy-mm-dd
 * Automatically determines century based on current year unless futureDate is true
 * @param {string} input - Date string in yymmdd format
 * @param {boolean} futureDate - Whether to treat the date as a future date (forces 20xx)
 * @returns {string} Date string in yyyy-mm-dd format
 */
function convertDateFormat(input, futureDate = false) {
    var yearSuffix = input.slice(0, 2);
    var currentYearSuffix = new Date().getFullYear().toString().slice(2, 4);
    var yearPrefix;

    if (futureDate) {
        yearPrefix = "20";
    } else {
        yearPrefix = (parseInt(yearSuffix, 10) <= parseInt(currentYearSuffix, 10)) ? "20" : "19";
    }

    var year = yearPrefix + yearSuffix;
    var month = input.slice(2, 4);
    var day = input.slice(4, 6);

    // create a new Date object (months are 0-indexed in JavaScript)
    var date = new Date(year, month - 1, day);

    // convert the Date object to ISO string and split on 'T'
    var output = date.toISOString().split('T')[0];

    return output;
}

/**
 * Formats a currency field using the jQuery Mask plugin
 * @param {jQuery} el - jQuery element to apply currency mask to
 * @param {number} decimals - Number of decimal places (default: 0)
 * @param {string} prefix - Currency prefix (default: 'Rp')
 * @param {string} thousands_symbol - Thousands separator (default: '.')
 * @param {string} decimal_symbol - Decimal separator (default: ',')
 */
function formatCurrency(el, decimals = 0, prefix = 'Rp', thousands_symbol = '.', decimal_symbol = ',') {
    var decimals = parseInt("{{ currency_decimal_places }}");
    var msk_decimals = '';
    var msk = '000' + thousands_symbol;
    const thousands_places = 5;
    for (var i = 0; i < thousands_places; i++) {
        msk = '000' + thousands_symbol + msk;
    }
    for (var i = 0; i < decimals; i++) {
        if (i === 0) {
            msk_decimals += '.';
        }
        msk_decimals += '0';
    }
    msk += msk_decimals;
    setTimeout(function () {
        el.mask(msk, { reverse: true });
    }, 0);
}

/**
 * Removes currency formatting from a field to get the numeric value
 * @param {jQuery} el - jQuery element with currency mask
 * @param {number} decimals - Number of decimal places
 * @param {string} thousands_symbol - Thousands separator (default: '.')
 * @param {string} decimal_symbol - Decimal separator (default: ',')
 * @returns {number} The unformatted numeric value
 */
function unformatCurrency(el, decimals, thousands_symbol = '.', decimal_symbol = ',') {
    var unformatted = el.unmask();
    unformatted = unformatted.replace(thousands_symbol, '');
    if (decimals > 0) {
        unformatted = unformatted.replace(decimal_symbol, '.');
    }
    return parseFloat(unformatted);
}

/**
 * Rounds a value to the specified number of decimal places
 * @param {number} value - The value to round
 * @param {number} decimals - Number of decimal places (default: 0)
 * @returns {string} The rounded value as a string with fixed decimal places
 */
function roundToCurrencyDecimalPlaces(value, decimals = 0) {
    v = parseFloat(value);
    return v.toFixed(decimals);
}

/**
 * Capitalizes the first letter of a string
 * @param {string} string - The string to capitalize
 * @returns {string} The string with the first letter capitalized
 */
function capitalizeFirstLetter(string) {
    return string.charAt(0).toUpperCase() + string.slice(1);
}

/**
 * Formats a number as currency using Intl.NumberFormat
 * @param {number} amount - The amount to format
 * @param {string} currency - The currency code (default: 'IDR')
 * @param {string} locale - The locale to use for formatting (default: 'id-ID')
 * @returns {string} The formatted currency string
 */
function formatCurrencyValue(amount, currency = 'IDR', locale = 'id-ID') {
    return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: currency
    }).format(amount);
}

/**
 * Displays a success message using Bootstrap alert
 * Creates or updates an alert element with the success message
 * @param {string} message - The success message to display
 * @param {string} containerId - Optional container ID to append the alert to (default: body)
 */
function showSuccessMessage(message, containerId = null) {
    const alertHtml = `
        <div class="alert alert-success alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    if (containerId) {
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = alertHtml;
        }
    } else {
        // Insert at the top of the main content area
        const mainContent = document.querySelector('.main-content') || document.body;
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = alertHtml;
        mainContent.insertBefore(tempDiv.firstElementChild, mainContent.firstChild);
    }
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        const alerts = document.querySelectorAll('.alert-success');
        alerts.forEach(alert => {
            if (alert.textContent.includes(message)) {
                alert.classList.remove('show');
                setTimeout(() => alert.remove(), 150);
            }
        });
    }, 5000);
}

/**
 * Displays an error message using Bootstrap alert
 * Creates or updates an alert element with the error message
 * @param {string} message - The error message to display
 * @param {string} containerId - Optional container ID to append the alert to (default: body)
 */
function showErrorMessage(message, containerId = null) {
    const alertHtml = `
        <div class="alert alert-danger alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    if (containerId) {
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = alertHtml;
        }
    } else {
        // Insert at the top of the main content area
        const mainContent = document.querySelector('.main-content') || document.body;
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = alertHtml;
        mainContent.insertBefore(tempDiv.firstElementChild, mainContent.firstChild);
    }
}

/**
 * Handles AJAX errors with user-friendly messages
 * @param {Error|Object} error - The error object from fetch or AJAX call
 * @param {string} defaultMessage - Default message to show if error details unavailable
 * @returns {string} The error message to display
 */
function handleAjaxError(error, defaultMessage = 'An error occurred. Please try again.') {
    let errorMessage = defaultMessage;
    
    if (error && error.message) {
        errorMessage = error.message;
    } else if (typeof error === 'string') {
        errorMessage = error;
    }
    
    console.error('AJAX Error:', error);
    return errorMessage;
}

/**
 * Capitalizes each word in a string
 * @param {string} str - The string to capitalize
 * @returns {string} The string with each word capitalized
 */
function capitalizeWords(str) {
    return str.replace(/\b\w/g, char => char.toUpperCase());
}
