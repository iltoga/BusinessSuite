from django.db.models import Exists, Max, OuterRef

from core.components.unicorn_search_list_view import UnicornSearchListView
from customer_applications.models import DocApplication
from customer_applications.models.doc_workflow import DocWorkflow


class DocapplicationListView(UnicornSearchListView):
    model = DocApplication
    model_search_method = "search_doc_applications"
    start_search_at = 1
    order_by = ""
    hide_finished = True
    hide_not_started = False

    def handle_hide_finished(self):
        self.search()  # search again after hide_finished value changes

    def handle_hide_not_started(self):
        self.search()  # search again after hide_finished value changes

    def apply_filters(self, queryset):
        queryset = super().apply_filters(queryset)  # Call parent class method
        if self.hide_finished:
            queryset = queryset.exclude(status="completed")
        if self.hide_not_started:
            # exclude the applications that have no workflows
            has_workflow = Exists(DocWorkflow.objects.filter(doc_application=OuterRef("pk")))
            queryset = queryset.filter(has_workflow)

        return queryset

    def get_queryset(self):
        if self.query:
            search_func = getattr(self.model.objects, self.model_search_method)
            queryset = search_func(self.query)
        else:
            queryset = self.model.objects.all()

        if self.order_by == "wf_due_date":
            queryset = queryset.annotate(max_due_date=Max("workflows__due_date"))

        queryset = self.apply_filters(queryset)

        # Unpack the list when calling order_by
        queryset = queryset.order_by(*self.get_order())

        return queryset

    def get_order(self):
        if self.order_by == "":
            if self.model._meta.ordering is None or len(self.model._meta.ordering) == 0:
                return ["id"]
            return self.model._meta.ordering

        if self.order_by == "wf_due_date":
            return ["max_due_date"] if self.sort_dir == "asc" else ["-max_due_date"]
        else:
            return [self.order_by] if self.sort_dir == "asc" else ["-" + self.order_by]
