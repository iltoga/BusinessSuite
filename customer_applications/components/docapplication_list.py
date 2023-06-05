from customer_applications.models import DocApplication
from core.components.unicorn_search_list_view import UnicornSearchListView

class DocapplicationListView(UnicornSearchListView):
    model = DocApplication
    model_search_method = 'search_doc_applications'
    start_search_at = 1

