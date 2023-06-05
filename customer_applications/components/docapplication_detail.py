from django_unicorn.components import UnicornView
from core.components.unicorn_model_view import UnicornModelView
from customer_applications.models import DocApplication

class DocapplicationDetailView(UnicornModelView):
    model = DocApplication