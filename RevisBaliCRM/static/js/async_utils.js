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
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken
        };
        options.body = JSON.stringify(data);
    }

    // Perform the fetch
    fetch(url, options)
        .then(response => {
            if (!response.ok) {
                throw Error(response.statusText);
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
