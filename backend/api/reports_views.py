from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from core.models.ai_request_usage import AIRequestUsage
from django.utils import timezone
from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear, TruncDate
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
        keys = [
            "top_customers",
            "total_customers",
            "total_revenue",
            "total_revenue_formatted",
            "avg_customer_value",
            "avg_customer_value_formatted",
            "high_value_count",
            "medium_value_count",
            "low_value_count",
        ]
        return Response({k: _to_json_value(ctx.get(k)) for k in keys})


class ApplicationPipelineApiView(_BaseReportAPIView):
    report_view_cls = ApplicationPipelineView

    def get(self, request):
        ctx = self.build_context(request)
        recent_applications = [
            {
                "id": application.id,
                # DocApplication has no doc_no field; expose a stable readable reference.
                "doc_no": getattr(application, "doc_no", f"APP-{application.id}"),
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


class AICostingReportApiView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _parse_int(value: str | None, default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value: Decimal | int | float | None) -> float:
        if value is None:
            return 0.0
        return float(value)

    def get(self, request):
        now = timezone.localtime()
        selected_year = self._parse_int(request.GET.get("year"), now.year)
        selected_month = self._parse_int(request.GET.get("month"), now.month)
        selected_month = min(max(selected_month, 1), 12)

        base_qs = AIRequestUsage.objects.all()
        available_years = (
            base_qs.annotate(year=ExtractYear("created_at"))
            .values_list("year", flat=True)
            .order_by("year")
            .distinct()
        )
        available_years = [int(year) for year in available_years if year is not None]
        if not available_years:
            available_years = [selected_year]

        if selected_year not in available_years:
            selected_year = max(available_years)

        yearly_rows = (
            base_qs.annotate(year=ExtractYear("created_at"))
            .values("year")
            .annotate(
                request_count=Count("id"),
                success_count=Count("id", filter=Q(success=True)),
                failed_count=Count("id", filter=Q(success=False)),
                total_tokens=Coalesce(Sum("total_tokens"), 0),
                total_cost=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
            )
            .order_by("year")
        )

        yearly_data = [
            {
                "year": int(row["year"]),
                "requestCount": int(row["request_count"]),
                "successCount": int(row["success_count"]),
                "failedCount": int(row["failed_count"]),
                "totalTokens": int(row["total_tokens"] or 0),
                "totalCost": self._as_float(row["total_cost"]),
            }
            for row in yearly_rows
            if row.get("year") is not None
        ]

        monthly_qs = (
            base_qs.filter(created_at__year=selected_year)
            .annotate(month=ExtractMonth("created_at"))
            .values("month")
            .annotate(
                request_count=Count("id"),
                success_count=Count("id", filter=Q(success=True)),
                failed_count=Count("id", filter=Q(success=False)),
                total_tokens=Coalesce(Sum("total_tokens"), 0),
                total_cost=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
            )
            .order_by("month")
        )
        monthly_map = {int(row["month"]): row for row in monthly_qs if row.get("month") is not None}
        monthly_data: list[dict[str, Any]] = []
        for month_num in range(1, 13):
            row = monthly_map.get(month_num, {})
            monthly_data.append(
                {
                    "month": month_num,
                    "label": calendar.month_abbr[month_num],
                    "requestCount": int(row.get("request_count") or 0),
                    "successCount": int(row.get("success_count") or 0),
                    "failedCount": int(row.get("failed_count") or 0),
                    "totalTokens": int(row.get("total_tokens") or 0),
                    "totalCost": self._as_float(row.get("total_cost")),
                }
            )

        month_qs = base_qs.filter(created_at__year=selected_year, created_at__month=selected_month)
        daily_qs = (
            month_qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                request_count=Count("id"),
                success_count=Count("id", filter=Q(success=True)),
                failed_count=Count("id", filter=Q(success=False)),
                total_tokens=Coalesce(Sum("total_tokens"), 0),
                total_cost=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
            )
            .order_by("day")
        )
        daily_map = {row["day"]: row for row in daily_qs if row.get("day")}
        days_in_month = calendar.monthrange(selected_year, selected_month)[1]
        daily_data: list[dict[str, Any]] = []
        for day_num in range(1, days_in_month + 1):
            day_date = date(selected_year, selected_month, day_num)
            row = daily_map.get(day_date, {})
            daily_data.append(
                {
                    "date": day_date.isoformat(),
                    "label": day_date.strftime("%d %b"),
                    "requestCount": int(row.get("request_count") or 0),
                    "successCount": int(row.get("success_count") or 0),
                    "failedCount": int(row.get("failed_count") or 0),
                    "totalTokens": int(row.get("total_tokens") or 0),
                    "totalCost": self._as_float(row.get("total_cost")),
                }
            )

        def _group_breakdown(qs, group_field: str, key_name: str) -> list[dict[str, Any]]:
            rows = (
                qs.values(group_field)
                .annotate(
                    request_count=Count("id"),
                    success_count=Count("id", filter=Q(success=True)),
                    failed_count=Count("id", filter=Q(success=False)),
                    total_tokens=Coalesce(Sum("total_tokens"), 0),
                    total_cost=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
                )
                .order_by("-total_cost", "-request_count")
            )
            payload: list[dict[str, Any]] = []
            for row in rows:
                payload.append(
                    {
                        key_name: row.get(group_field) or "Unknown",
                        "requestCount": int(row["request_count"]),
                        "successCount": int(row["success_count"]),
                        "failedCount": int(row["failed_count"]),
                        "totalTokens": int(row["total_tokens"] or 0),
                        "totalCost": self._as_float(row["total_cost"]),
                    }
                )
            return payload

        feature_breakdown_month = _group_breakdown(month_qs, "feature", "feature")
        provider_breakdown_month = _group_breakdown(month_qs, "provider", "provider")
        model_breakdown_month = _group_breakdown(month_qs, "model", "model")

        year_summary_row = (
            base_qs.filter(created_at__year=selected_year).aggregate(
                request_count=Count("id"),
                success_count=Count("id", filter=Q(success=True)),
                failed_count=Count("id", filter=Q(success=False)),
                total_tokens=Coalesce(Sum("total_tokens"), 0),
                total_cost=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
            )
        )
        month_summary_row = month_qs.aggregate(
            request_count=Count("id"),
            success_count=Count("id", filter=Q(success=True)),
            failed_count=Count("id", filter=Q(success=False)),
            total_tokens=Coalesce(Sum("total_tokens"), 0),
            total_cost=Coalesce(Sum("cost_usd"), Value(Decimal("0"))),
        )

        return Response(
            {
                "selectedYear": selected_year,
                "selectedMonth": selected_month,
                "selectedMonthLabel": calendar.month_name[selected_month],
                "availableYears": available_years,
                "yearSummary": {
                    "requestCount": int(year_summary_row["request_count"] or 0),
                    "successCount": int(year_summary_row["success_count"] or 0),
                    "failedCount": int(year_summary_row["failed_count"] or 0),
                    "totalTokens": int(year_summary_row["total_tokens"] or 0),
                    "totalCost": self._as_float(year_summary_row["total_cost"]),
                },
                "monthSummary": {
                    "requestCount": int(month_summary_row["request_count"] or 0),
                    "successCount": int(month_summary_row["success_count"] or 0),
                    "failedCount": int(month_summary_row["failed_count"] or 0),
                    "totalTokens": int(month_summary_row["total_tokens"] or 0),
                    "totalCost": self._as_float(month_summary_row["total_cost"]),
                },
                "yearlyData": yearly_data,
                "monthlyData": monthly_data,
                "dailyData": daily_data,
                "featureBreakdownMonth": feature_breakdown_month,
                "providerBreakdownMonth": provider_breakdown_month,
                "modelBreakdownMonth": model_breakdown_month,
            }
        )
