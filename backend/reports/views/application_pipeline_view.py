from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.views.generic import TemplateView

from customer_applications.models import DocApplication, DocWorkflow
from products.models import Product


class ApplicationPipelineView(LoginRequiredMixin, TemplateView):
    """Customer application processing status and workflow tracking."""

    template_name = "reports/application_pipeline.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Applications by status
        status_data = []
        for status_code, status_label in DocApplication.STATUS_CHOICES:
            count = DocApplication.objects.filter(status=status_code).count()
            status_data.append(
                {
                    "status": status_label,
                    "code": status_code,
                    "count": count,
                }
            )

        # Document collection completion rate
        total_applications = DocApplication.objects.count()

        # Applications with all required documents completed
        from django.db.models import F

        completed_doc_collection = (
            DocApplication.objects.annotate(
                total_required=Count("documents", filter=Q(documents__required=True)),
                completed_required=Count("documents", filter=Q(documents__required=True, documents__completed=True)),
            )
            .filter(total_required=F("completed_required"))
            .count()
        )

        doc_completion_rate = (completed_doc_collection / total_applications * 100) if total_applications > 0 else 0

        # Average processing time by product type
        from datetime import timedelta

        processing_time_data = []

        for product in Product.objects.all()[:10]:  # Top 10 products
            completed_apps = DocApplication.objects.filter(product=product, status=DocApplication.STATUS_COMPLETED)

            if completed_apps.exists():
                total_days = 0
                count = 0

                for app in completed_apps:
                    # Use updated_at as completion date for completed applications
                    if app.updated_at and app.doc_date:
                        completion_date = app.updated_at.date()
                        days = (completion_date - app.doc_date).days
                        total_days += days
                        count += 1

                avg_days = total_days / count if count > 0 else 0

                processing_time_data.append({"product": product.name, "avg_days": round(avg_days, 1), "count": count})

        # Sort by average days descending (bottlenecks first)
        processing_time_data.sort(key=lambda x: x["avg_days"], reverse=True)

        # Workflow task performance
        workflow_data = []
        all_workflows = DocWorkflow.objects.select_related("task")

        # Group by task
        from collections import defaultdict

        task_stats = defaultdict(lambda: {"completed": 0, "pending": 0, "overdue": 0, "total_days": 0})

        now = timezone.now().date()
        for workflow in all_workflows:
            task_name = workflow.task.name
            is_completed = workflow.status == DocWorkflow.STATUS_COMPLETED
            task_stats[task_name]["completed" if is_completed else "pending"] += 1

            if not is_completed and workflow.due_date and workflow.due_date < now:
                task_stats[task_name]["overdue"] += 1

            if is_completed and workflow.completion_date and workflow.start_date:
                days = (workflow.completion_date - workflow.start_date).days
                task_stats[task_name]["total_days"] += days

        for task_name, stats in task_stats.items():
            total = stats["completed"] + stats["pending"]
            completion_rate = (stats["completed"] / total * 100) if total > 0 else 0
            avg_days = stats["total_days"] / stats["completed"] if stats["completed"] > 0 else 0

            workflow_data.append(
                {
                    "task": task_name,
                    "completed": stats["completed"],
                    "pending": stats["pending"],
                    "overdue": stats["overdue"],
                    "completion_rate": round(completion_rate, 1),
                    "avg_days": round(avg_days, 1),
                }
            )

        # Sort by completion rate ascending (bottlenecks first)
        workflow_data.sort(key=lambda x: x["completion_rate"])

        # Recent applications
        recent_applications = DocApplication.objects.select_related("customer", "product").order_by("-doc_date")[:10]

        context.update(
            {
                "status_data": status_data,
                "total_applications": total_applications,
                "completed_doc_collection": completed_doc_collection,
                "doc_completion_rate": round(doc_completion_rate, 1),
                "processing_time_data": processing_time_data[:10],
                "workflow_data": workflow_data[:10],
                "recent_applications": recent_applications,
            }
        )

        return context
