from core.components.unicorn_search_list_view import UnicornSearchListView
from payments.models import Payment


class PaymentListView(UnicornSearchListView):
    model = Payment
    model_search_method = "search_payments"
