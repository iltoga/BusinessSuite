from products.models import Product
from core.components.unicorn_search_list_view import UnicornSearchListView

class ProductListView(UnicornSearchListView):
    model = Product
    model_search_method = 'search_products'
    start_search_at = 2
