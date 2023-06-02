from products.models import Product
from core.components.search_list_view import SearchListView

class ProductListView(SearchListView):
    model = Product
    model_search_method = 'search_products'
    start_search_at = 2
