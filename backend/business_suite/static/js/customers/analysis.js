/**
 * @module customers/analysis
 * @description Handles customer analysis page interactions including:
 *   - Chart type selection and navigation
 * @requires jQuery
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';
    
    /**
     * Initialize customer analysis page functionality
     */
    function initCustomerAnalysis() {
        const plotTypeSelect = $('#plot_type');
        
        if (plotTypeSelect.length === 0) {
            return; // Element not found, exit gracefully
        }
        
        // Handle chart type selection change
        plotTypeSelect.on('change', function() {
            const plotType = $(this).val();
            const urlTemplate = plotTypeSelect.data('url-template');
            
            if (urlTemplate && plotType) {
                const url = urlTemplate.replace('placeholder', plotType);
                window.location.href = url;
            }
        });
    }
    
    // Auto-initialize on DOM ready
    $(document).ready(initCustomerAnalysis);
})();
