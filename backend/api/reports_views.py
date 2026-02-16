from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.utils import timezone
from reports.views.application_pipeline_view import ApplicationPipelineView
from reports.views.cash_flow_analysis_view import CashFlowAnalysisView
from reports.views.customer_ltv_view import CustomerLifetimeValueView
from reports.views.invoice_status_dashboard_view import InvoiceStatusDashboardView
from reports.views.kpi_dashboard_view import KPIDashboardView
from reports.views.monthly_invoice_detail_view import MonthlyInvoiceDetailView
from reports.views.product_demand_forecast_view import ProductDemandForecastView
from reports.views.product_revenue_analysis_view import ProductRevenueAnalysisView
from reports.views.reports_index_view import ReportsIndexView
from reports.views.revenue_report_view import RevenueReportView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def _to_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_to_json_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_json_value(v) for k, v in value.items()}
    return value


def _serialize_ltv_customers(customers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return JSON-safe LTV rows and strip non-serializable model references."""

    serialized_customers: list[dict[str, Any]] = []
    for customer_row in customers:
        if not isinstance(customer_row, dict):
            continue

        serialized_row = {k: v for k, v in customer_row.items() if k != "customer"}
        serialized_customers.append(_to_json_value(serialized_row))

    return serialized_customers


class _BaseReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    report_view_cls: type | None = None

    def build_context(self, request) -> dict[str, Any]:
        if self.report_view_cls is None:
            return {}

        view = self.report_view_cls()
        view.request = request
        view.args = ()
        view.kwargs = {}
        return view.get_context_data()


class ReportsIndexApiView(_BaseReportAPIView):
    report_view_cls = ReportsIndexView

    def get(self, request):
        ctx = self.build_context(request)
        return Response({"reports": ctx.get("reports", [])})


class RevenueReportApiView(_BaseReportAPIView):
    report_view_cls = RevenueReportView

    def get(self, request):
        ctx = self.build_context(request)
        keys = [
            "from_date",
            "to_date",
            "monthly_revenue",
            "total_invoiced",
            "total_invoiced_formatted",
            "total_paid",
            "total_paid_formatted",
            "total_outstanding",
            "total_outstanding_formatted",
            "collection_rate",
            "yoy_data",
        ]
        return Response({k: _to_json_value(ctx.get(k)) for k in keys})


class KPIDashboardApiView(_BaseReportAPIView):
    report_view_cls = KPIDashboardView

    def get(self, request):
        ctx = self.build_context(request)

        top_customers = [
            {
                "name": customer.full_name,
                "id": customer.id,
                "total_revenue": float(customer.total_revenue or 0),
            }
            for customer in ctx.get("top_customers", [])
        ]
        recent_payments = [
            {
                "id": payment.id,
                "payment_date": payment.payment_date.isoformat(),
                "amount": float(payment.amount),
                "invoice_no": payment.invoice_application.invoice.invoice_no,
            }
            for payment in ctx.get("recent_payments", [])
        ]

        keys = [
            "timeframe",
            "period_label",
            "revenue_mtd",
            "revenue_mtd_formatted",
            "revenue_trend",
            "revenue_change",
            "revenue_period",
            "revenue_period_formatted",
            "revenue_ytd",
            "revenue_ytd_formatted",
            "outstanding_amount",
            "outstanding_formatted",
            "active_applications",
            "overdue_invoices",
            "chart_data",
            "chart_label",
        ]
        payload = {k: _to_json_value(ctx.get(k)) for k in keys}
        payload["top_customers"] = top_customers
        payload["recent_payments"] = recent_payments
        return Response(payload)


class InvoiceStatusDashboardApiView(_BaseReportAPIView):
    report_view_cls = InvoiceStatusDashboardView

    def get(self, request):
        ctx = self.build_context(request)
        keys = ["status_data", "aging_data", "avg_days_to_payment", "collection_rate"]
        return Response({k: _to_json_value(ctx.get(k)) for k in keys})


class MonthlyInvoiceDetailApiView(_BaseReportAPIView):
    report_view_cls = MonthlyInvoiceDetailView

    def get(self, request):
        ctx = self.build_context(request)
        invoices = [
            {
                **invoice,
                "invoice_date": invoice["invoice_date"].isoformat() if invoice.get("invoice_date") else None,
                "due_date": invoice["due_date"].isoformat() if invoice.get("due_date") else None,
                "customer_passport_expiration_date": (
                    invoice["customer_passport_expiration_date"].isoformat()
                    if invoice.get("customer_passport_expiration_date")
                    else None
                ),
            }
            for invoice in ctx.get("invoices", [])
        ]

        keys = [
            "selected_month",
            "selected_year",
            "month_name",
            "months",
            "years",
            "total_invoices",
            "total_amount",
            "total_amount_formatted",
            "total_paid",
            "total_paid_formatted",
            "total_due",
            "total_due_formatted",
        ]
        payload = {k: _to_json_value(ctx.get(k)) for k in keys}
        payload["invoices"] = invoices
        return Response(payload)


class CashFlowAnalysisApiView(_BaseReportAPIView):
    report_view_cls = CashFlowAnalysisView

    def get(self, request):
        ctx = self.build_context(request)
        keys = [
            "from_date",
            "to_date",
            "payment_type_data",
            "monthly_cashflow",
            "running_balance",
            "daily_cashflow",
            "total_cashflow",
            "total_cashflow_formatted",
            "avg_monthly_cashflow",
            "avg_monthly_cashflow_formatted",
            "total_transactions",
        ]
        return Response({k: _to_json_value(ctx.get(k)) for k in keys})


class CustomerLifetimeValueApiView(_BaseReportAPIView):
    report_view_cls = CustomerLifetimeValueView

    def get(self, request):
        ctx = self.build_context(request)

        top_customers = _serialize_ltv_customers(ctx.get("top_customers", []))
        if not top_customers:
            top_customers = _serialize_ltv_customers(ctx.get("all_customers", []))

        keys = [
            "total_customers",
            "total_revenue",
            "total_revenue_formatted",
            "avg_customer_value",
            "avg_customer_value_formatted",
            "high_value_count",
            "medium_value_count",
            "low_value_count",
        ]
        payload = {k: _to_json_value(ctx.get(k)) for k in keys}
        payload["top_customers"] = top_customers
        return Response(payload)


class ApplicationPipelineApiView(_BaseReportAPIView):
    report_view_cls = ApplicationPipelineView

    def get(self, request):
        ctx = self.build_context(request)
        recent_applications = [
            {
                "id": application.id,
                "doc_no": application.doc_no,
                "doc_date": application.doc_date.isoformat() if application.doc_date else None,
                "status": application.status,
                "status_label": application.get_status_display(),
                "customer_name": application.customer.full_name if application.customer else "",
                "product_name": application.product.name if application.product else "",
            }
            for application in ctx.get("recent_applications", [])
        ]

        keys = [
            "status_data",
            "total_applications",
            "completed_doc_collection",
            "doc_completion_rate",
            "processing_time_data",
            "workflow_data",
        ]
        payload = {k: _to_json_value(ctx.get(k)) for k in keys}
        payload["recent_applications"] = recent_applications
        return Response(payload)


class ProductRevenueAnalysisApiView(_BaseReportAPIView):
    report_view_cls = ProductRevenueAnalysisView

    def get(self, request):
        ctx = self.build_context(request)
        product_data = [
            {
                **row,
                "product": {
                    "id": row["product"].id,
                    "code": row["product"].code,
                    "name": row["product"].name,
                },
            }
            for row in ctx.get("product_data", [])
        ]

        keys = [
            "type_data",
            "monthly_trends",
            "top_products",
            "total_products",
            "total_revenue",
            "total_revenue_formatted",
            "total_applications",
        ]
        payload = {k: _to_json_value(ctx.get(k)) for k in keys}
        payload["product_data"] = _to_json_value(product_data)
        return Response(payload)


class ProductDemandForecastApiView(_BaseReportAPIView):
    report_view_cls = ProductDemandForecastView

    def get(self, request):
        ctx = self.build_context(request)
        keys = ["top_products", "product_demand", "growth_rates", "forecast_data", "quarterly_data", "total_by_month"]
        return Response({k: _to_json_value(ctx.get(k)) for k in keys})
