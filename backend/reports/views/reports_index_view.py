from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class ReportsIndexView(LoginRequiredMixin, TemplateView):
    """Main reports landing page with links to all reports."""

    template_name = "reports/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["reports"] = [
            {
                "name": "KPI Dashboard",
                "description": "Executive dashboard with key performance indicators",
                "url": "report-kpi-dashboard",
                "icon": "bi-speedometer2",
                "category": "Overview",
            },
            {
                "name": "Revenue Report",
                "description": "Monthly and yearly revenue analysis",
                "url": "report-revenue",
                "icon": "bi-graph-up",
                "category": "Financial",
            },
            {
                "name": "Invoice Status Dashboard",
                "description": "Track invoice status and aging",
                "url": "report-invoice-status",
                "icon": "bi-file-earmark-text",
                "category": "Financial",
            },
            {
                "name": "Monthly Invoice Details",
                "description": "Detailed invoice listing by month with Excel export",
                "url": "report-monthly-invoices",
                "icon": "bi-file-earmark-spreadsheet",
                "category": "Financial",
            },
            {
                "name": "Cash Flow Analysis",
                "description": "Payment tracking by type and date",
                "url": "report-cash-flow",
                "icon": "bi-cash-stack",
                "category": "Financial",
            },
            {
                "name": "Customer Lifetime Value",
                "description": "Top customers by revenue",
                "url": "report-customer-ltv",
                "icon": "bi-people",
                "category": "Customer",
            },
            {
                "name": "Application Pipeline",
                "description": "Customer application processing status",
                "url": "report-application-pipeline",
                "icon": "bi-kanban",
                "category": "Operations",
            },
            {
                "name": "Product Revenue Analysis",
                "description": "Product performance and revenue breakdown",
                "url": "report-product-revenue",
                "icon": "bi-box-seam",
                "category": "Product",
            },
            {
                "name": "Product Demand Forecast",
                "description": "Seasonal trends and demand predictions",
                "url": "report-product-demand",
                "icon": "bi-graph-up-arrow",
                "category": "Product",
            },
            {
                "name": "AI Costing Intelligence",
                "description": "Track AI usage costs by year, month, and day",
                "url": "report-ai-costing",
                "icon": "bi-cpu",
                "category": "Operations",
            },
        ]
        return context
