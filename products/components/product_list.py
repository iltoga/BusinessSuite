from core.components.unicorn_search_list_view import UnicornSearchListView
from products.models import Product


class ProductListView(UnicornSearchListView):
    model = Product
    model_search_method = "search_products"
    items_per_page = 15
