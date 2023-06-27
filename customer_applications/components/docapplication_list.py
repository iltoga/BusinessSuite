from django.db.models import Exists, Max, OuterRef

from core.components.unicorn_search_list_view import UnicornSearchListView
from customer_applications.models import DocApplication
from customer_applications.models.doc_workflow import DocWorkflow


class DocapplicationListView(UnicornSearchListView):
    model = DocApplication
    model_search_method = "search_doc_applications"
    start_search_at = 0
    order_by = ""
    hide_finished = True
    hide_not_started = False

    def handle_hide_finished(self):
        # Trigger a new search when hide_finished value changes
        self.search()

    def handle_hide_not_started(self):
        # Trigger a new search when hide_not_started value changes
        self.search()

    def apply_filters(self, queryset):
        # Call parent class method first
        queryset = super().apply_filters(queryset)
        # Apply filters based on component's state
        queryset = self.apply_status_filters(queryset)
        return queryset

    def get_queryset(self):
        queryset = self.get_initial_queryset()
        queryset = self.apply_due_date_annotation(queryset)
        queryset = self.apply_filters(queryset)
        # Unpack the list when calling order_by
        queryset = queryset.order_by(*self.get_order())
        return queryset

    # Custom methods
    def get_initial_queryset(self):
        """Retrieve the initial queryset based on the search query or return all records."""
        if self.query:
            search_func = getattr(self.model.objects, self.model_search_method)
            return search_func(self.query)
        else:
            return self.model.objects.all()

    def apply_status_filters(self, queryset):
        """Exclude records based on their status."""
        if self.hide_finished:
            queryset = queryset.exclude(status="completed")
        if self.hide_not_started:
            queryset = self.exclude_without_workflows(queryset)
        return queryset

    def exclude_without_workflows(self, queryset):
        """Exclude the applications that have no workflows."""
        has_workflow = Exists(DocWorkflow.objects.filter(doc_application=OuterRef("pk")))
        return queryset.filter(has_workflow)

    def apply_due_date_annotation(self, queryset):
        """Apply due date annotation to the queryset."""
        if self.order_by == "wf_due_date":
            queryset = queryset.annotate(max_due_date=Max("workflows__due_date"))
        return queryset

    def get_order(self):
        """Determine the ordering for the queryset."""
        if not self.order_by:
            return self.model._meta.ordering or ["id"]

        if self.order_by == "wf_due_date":
            return self.get_due_date_ordering()
        else:
            return [self.order_by] if self.sort_dir == "asc" else [f"-{self.order_by}"]

    def get_due_date_ordering(self):
        """Return the ordering string for due date."""
        return ["max_due_date"] if self.sort_dir == "asc" else ["-max_due_date"]
