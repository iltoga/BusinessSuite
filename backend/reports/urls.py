from django.urls import path

from .views import (
    ApplicationPipelineView,
    CashFlowAnalysisView,
    CustomerLifetimeValueView,
    InvoiceStatusDashboardView,
    KPIDashboardView,
    MonthlyInvoiceDetailView,
    ProductDemandForecastView,
    ProductRevenueAnalysisView,
    ReportsIndexView,
    RevenueReportView,
)

urlpatterns = [
    path("", ReportsIndexView.as_view(), name="reports-index"),
    path("revenue/", RevenueReportView.as_view(), name="report-revenue"),
    path("kpi-dashboard/", KPIDashboardView.as_view(), name="report-kpi-dashboard"),
    path("invoice-status/", InvoiceStatusDashboardView.as_view(), name="report-invoice-status"),
    path("customer-ltv/", CustomerLifetimeValueView.as_view(), name="report-customer-ltv"),
    path("product-revenue/", ProductRevenueAnalysisView.as_view(), name="report-product-revenue"),
    path("cash-flow/", CashFlowAnalysisView.as_view(), name="report-cash-flow"),
    path("application-pipeline/", ApplicationPipelineView.as_view(), name="report-application-pipeline"),
    path("product-demand/", ProductDemandForecastView.as_view(), name="report-product-demand"),
    path("monthly-invoices/", MonthlyInvoiceDetailView.as_view(), name="report-monthly-invoices"),
]
