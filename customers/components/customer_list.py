from core.components.unicorn_search_list_view import UnicornSearchListView
from customers.models import Customer


class CustomerListView(UnicornSearchListView):
    model = Customer
    model_search_method = "search_customers"
    start_search_at = 3
