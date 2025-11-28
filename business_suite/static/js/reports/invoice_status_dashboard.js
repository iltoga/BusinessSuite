/* Status and Aging charts initialization.
   Reads JSON data from container data attributes.
*/
(function(){
    'use strict';
    function parseJsonData(jsonStr){
        try { return JSON.parse(jsonStr); } catch(e) { return []; }
    }
    function init(){
        var container = document.getElementById('report-status-dashboard');
        if (!container) return;
        var statusData = parseJsonData(container.dataset.statusData || '[]');
        var agingData = parseJsonData(container.dataset.agingData || '[]');

        var statusCtx = document.getElementById('statusChart');
        if (statusCtx && statusData.length) {
            new Chart(statusCtx.getContext('2d'), {
                type: 'doughnut',
                data: {
                    labels: statusData.map(d => d.status),
                    datasets: [{
                        data: statusData.map(d => d.total),
                        backgroundColor: ['#0d6efd', '#198754', '#ffc107', '#dc3545', '#6c757d', '#0dcaf0', '#d63384', '#20c997']
                    }]
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' } } }
            });
        }

        var agingCtx = document.getElementById('agingChart');
        if (agingCtx && agingData.length) {
            new Chart(agingCtx.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: agingData.map(d => d.label),
                    datasets: [{ label: 'Amount', data: agingData.map(d => d.total), backgroundColor: ['#198754', '#ffc107', '#fd7e14', '#dc3545'] }]
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
            });
        }
    }
    if (document.readyState !== 'loading') init(); else document.addEventListener('DOMContentLoaded', init);
})();
