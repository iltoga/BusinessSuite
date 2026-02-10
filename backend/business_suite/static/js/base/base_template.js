/**
 * @module base/base_template
 * @description Handles base template interactions including:
 *   - Sidebar collapse/expand functionality
 *   - Responsive sidebar behavior
 *   - Submenu state management
 *   - Active link tracking
 *   - Select2 initialization
 *   - Alert auto-dismiss
 * @requires jQuery
 * @requires select2
 * @validates Requirements 2.1, 2.2, 2.4, 4.3, 7.1
 */

(function() {
    'use strict';

    /**
     * Initialize base template functionality
     */
    function initBaseTemplate() {
        const SIDEBAR = $('#sidebar');
        const CONTENT = $('#content');
        const SIDEBAR_COLLAPSE = $('#sidebarCollapse');
        const COLLAPSE_LINKS = $('#sidebar .collapse a');

        // Check if sidebarCollapse is in localStorage
        if (!localStorage.getItem('sidebarCollapse')) {
            localStorage.setItem('sidebarCollapse', 'inactive');
        }

        /**
         * Adjust sidebar and content based on window width
         */
        function adjustView() {
            var win = $(window);

            if (win.width() >= 1280) {
                // if width is greater than or equal to 1280px, show sidebar
                SIDEBAR.show();
                CONTENT.removeClass('active');
                SIDEBAR_COLLAPSE.show();
            } else {
                // if width is less than 1280px, hide sidebar
                SIDEBAR.hide();
                CONTENT.addClass('active');
                SIDEBAR_COLLAPSE.hide();
            }
        }

        // Call adjustView initially and on window resize
        adjustView();
        $(window).on('resize', adjustView);

        // Check localStorage and set sidebar state
        let sidebarCollapseState = localStorage.getItem('sidebarCollapse');

        if (sidebarCollapseState === 'active') {
            // add active class to sidebar and content
            SIDEBAR.addClass('active');
            CONTENT.addClass('active');
        }

        // Initialize select2 dropdown
        $('.select2').select2();

        // Dismiss alerts: set the alert to automatically fade out
        $('.alert-dismissible').delay(5000).fadeOut("slow");

        // Restore submenu state from local storage (and support admin tools route)
        let opened_submenu = localStorage.getItem('opened_submenu');
        // If nothing saved but current path is under /admin-tools, default to adminToolsSubmenu
        if (!opened_submenu) {
            try {
                const p = window.location.pathname || '';
                if (p.startsWith('/admin-tools')) {
                    opened_submenu = 'adminToolsSubmenu';
                    localStorage.setItem('opened_submenu', opened_submenu);
                }
            } catch (e) {
                // ignore
            }
        }
        if (opened_submenu) {
            $("#" + opened_submenu).addClass('show');
            // set aria-expanded to true for the dropdown toggle of the opened submenu
            $('a[href="#' + opened_submenu + '"]').attr('aria-expanded', 'true');
        }

        // Restore active state of last selected item (or set based on current path)
        let activeLink = localStorage.getItem('active-link');
        if (!activeLink) {
            try {
                const p = window.location.pathname || '';
                // try to find a matching submenu link that equals the current path
                const match = $(`#sidebar .collapse a[href="${p}"]`);
                if (match.length) {
                    activeLink = p;
                    localStorage.setItem('active-link', activeLink);
                }
            } catch (e) {
                // ignore
            }
        }
        if (activeLink) {
            // remove 'active' class from all other links
            COLLAPSE_LINKS.removeClass('active');
            // set active link
            $(`#sidebar .collapse a[href="${activeLink}"]`).addClass('active');
        }

        // Sidebar collapse button click handler
        SIDEBAR_COLLAPSE.on('click', function() {
            if (SIDEBAR.hasClass('active')) {
                localStorage.setItem('sidebarCollapse', 'inactive');
                SIDEBAR.removeClass('active');
                CONTENT.removeClass('active');
            } else {
                localStorage.setItem('sidebarCollapse', 'active');
                SIDEBAR.addClass('active');
                CONTENT.addClass('active');
            }
        });

        // Handle dropdown toggle clicks in sidebar (not navbar dropdowns)
        $('#sidebar .dropdown-toggle').click(function(e) {
            e.preventDefault(); // Prevent default link behavior

            let href = $(this).attr("href");
            // Only handle sidebar collapsible submenus, not Bootstrap dropdowns
            if (!href || href === '#' || !href.startsWith('#')) {
                return;
            }

            let submenuId = href.substring(1); // Get the submenu ID from the href attribute
            let submenu = $("#" + submenuId);

            // Close all other submenus
            $('#sidebar .collapse').not(submenu).removeClass('show');
            $('#sidebar .dropdown-toggle').not(this).attr('aria-expanded', 'false');

            // Toggle current submenu
            if (submenu.hasClass('show')) {
                submenu.removeClass('show');
                $(this).attr('aria-expanded', 'false');
                localStorage.removeItem('opened_submenu');
            } else {
                submenu.addClass('show');
                $(this).attr('aria-expanded', 'true');
                localStorage.setItem('opened_submenu', submenuId);
            }
        });

        // Only target anchors in submenus for the click handler
        COLLAPSE_LINKS.on('click', function (e) {
            // remove 'active' class from all other links
            COLLAPSE_LINKS.removeClass('active');
            // add 'active' class to clicked link
            $(this).addClass('active');
            // save active link to local storage
            localStorage.setItem('active-link', $(this).attr('href'));
        });
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initBaseTemplate);
    } else {
        initBaseTemplate();
    }
})();
