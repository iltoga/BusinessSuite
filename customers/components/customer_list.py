from django_unicorn.components import UnicornView
from customers.models import Customer


class CustomerListView(UnicornView):
    customers = []
    search_input = ''
    page = 1
    items_per_page = 10

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self.customers = kwargs.get("customers")

    def mount(self):
        self.load_customers()

    def clear_states(self):
        self.customers = []
        self.search_input = ''

    def load_customers(self):
        self.customers = list(Customer.objects.all().values())

    def search(self):
        if self.search_input:
            self.customers = list(Customer.objects.search_customers(self.search_input)[self.items_per_page*(self.page-1):self.items_per_page*self.page].values())
            print(self.customers)
        else:
            self.load_customers()

    def next_page(self):
        self.page += 1
        self.load_customers()

    def previous_page(self):
        self.page -= 1 if self.page > 1 else 1
        self.load_customers()

