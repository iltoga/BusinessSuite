from customer_applications.models import DocApplication
from core.components.unicorn_search_list_view import UnicornSearchListView

class DocapplicationListView(UnicornSearchListView):
    model = DocApplication
    model_search_method = 'search_doc_applications'
    start_search_at = 1
    order_by = '-doc_date'
    # qry_filter_args = {
    #     'workflows__status': 'completed',
    #     'workflows__task__last_step': True
    # }

