from django_unicorn.components import UnicornView

class UnicornModelView(UnicornView):
    list_fields = []
    model = None
