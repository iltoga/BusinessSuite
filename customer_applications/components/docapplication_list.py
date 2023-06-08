from django.db.models import Exists, OuterRef
from customer_applications.models import DocApplication
from core.components.unicorn_search_list_view import UnicornSearchListView
from customer_applications.models.doc_workflow import DocWorkflow

class DocapplicationListView(UnicornSearchListView):
    model = DocApplication
    model_search_method = 'search_doc_applications'
    start_search_at = 1
    order_by = ''
    hide_finished = True
    hide_not_started = False

    def handle_hide_finished(self):
        self.search()  # search again after hide_finished value changes

    def handle_hide_not_started(self):
        self.search()  # search again after hide_finished value changes

    def apply_filters(self, queryset):
        queryset = super().apply_filters(queryset)  # Call parent class method
        if self.hide_finished:
            qry_filter_args = {
                'workflows__status': 'completed',
                'workflows__task__last_step': True
            }
            queryset = queryset.exclude(**qry_filter_args)

        if self.hide_not_started:
            # exclude the applications that have no workflows
            has_workflow = Exists(DocWorkflow.objects.filter(doc_application=OuterRef('pk')))
            queryset = queryset.filter(has_workflow)

        return queryset
