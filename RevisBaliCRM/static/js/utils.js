function restApiCall(method, url, data, successCallback, errorCallback) {
    // Function to get CSRF token
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

    // Configure the fetch options
    let options = {
        method: method,
        credentials: 'same-origin'
    };

    // If the method is not GET, include the CSRF token and set the body
    if (method.toUpperCase() !== 'GET') {
        let csrftoken = getCookie('csrftoken');
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

// Set the value of a form field based on the field type
// Note: specify a type for hidden fields
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
        case 'select-one':
        case 'select-multiple':
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

        default:
            console.error(`Unsupported field type: ${field.type}`);
            break;
    }
}

function getWeekNumber(d) {
    d = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
    var yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    var weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return weekNo;
}

// Convert date format from yymmdd to yyyy-mm-dd
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

// Format a currency field using the jQuery Mask plugin
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

// Unformat a currency field using the jQuery Mask plugin
function unformatCurrency(el, decimals, thousands_symbol = '.', decimal_symbol = ',') {
    var unformatted = el.unmask();
    unformatted = unformatted.replace(thousands_symbol, '');
    if (decimals > 0) {
        unformatted = unformatted.replace(decimal_symbol, '.');
    }
    return parseFloat(unformatted);
}

// Round to currency decimal places
function roundToCurrencyDecimalPlaces(value, decimals = 0) {
    v = parseFloat(value);
    return v.toFixed(decimals);
}

// Function to capitalize the first letter of a string
function capitalizeFirstLetter(string) {
    return string.charAt(0).toUpperCase() + string.slice(1);
}
