from customer_applications.models import DocApplication
from core.components.search_list_view import SearchListView

class DocapplicationListView(SearchListView):
    model = DocApplication
    model_search_method = 'search_doc_applications'
    start_search_at = 1

