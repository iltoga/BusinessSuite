/**
 * Document Actions Handler
 * 
 * Handles AJAX execution of document type hook actions.
 * Uses the restApiCall utility function from utils.js.
 */
(function() {
    'use strict';

    /**
     * Initialize document action button handlers
     */
    function init() {
        var actionButtons = document.querySelectorAll('.document-action-btn');
        if (!actionButtons.length) return;

        actionButtons.forEach(function(button) {
            button.addEventListener('click', handleActionClick);
        });
    }

    /**
     * Handle click on a document action button
     * @param {Event} e - The click event
     */
    function handleActionClick(e) {
        e.preventDefault();
        var button = e.currentTarget;
        var url = button.dataset.actionUrl;
        var actionName = button.dataset.actionName;
        var documentId = button.dataset.documentId;

        if (!url || !actionName) {
            showErrorMessage('Invalid action configuration');
            return;
        }

        // Show loading state
        setButtonLoading(button, true);

        // Make the API call
        restApiCall('POST', url, {},
            function(data) {
                setButtonLoading(button, false);
                if (data.success) {
                    showSuccessMessage(data.message || 'Action completed successfully');
                    // Reload the page to show updated document
                    setTimeout(function() {
                        window.location.reload();
                    }, 1500);
                } else {
                    showErrorMessage(data.error || 'Action failed');
                }
            },
            function(error) {
                setButtonLoading(button, false);
                var errorMessage = handleAjaxError(error, 'Failed to execute action');
                showErrorMessage(errorMessage);
            }
        );
    }

    /**
     * Set the loading state of a button
     * @param {HTMLElement} button - The button element
     * @param {boolean} loading - Whether to show loading state
     */
    function setButtonLoading(button, loading) {
        var spinner = button.querySelector('.spinner-border');
        if (loading) {
            button.disabled = true;
            if (spinner) {
                spinner.classList.remove('d-none');
            }
        } else {
            button.disabled = false;
            if (spinner) {
                spinner.classList.add('d-none');
            }
        }
    }

    // Initialize when DOM is ready
    if (document.readyState !== 'loading') {
        init();
    } else {
        document.addEventListener('DOMContentLoaded', init);
    }

})();
