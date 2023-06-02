from customers.models import Customer
from core.components.search_list_view import SearchListView

class CustomerListView(SearchListView):
    model = Customer
    model_search_method = 'search_customers'
    start_search_at = 3
