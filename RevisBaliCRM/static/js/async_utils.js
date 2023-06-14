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
                const error = await response.json();
                throw Error(error.message); // Assume server sends { "message": "Error details" }
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
