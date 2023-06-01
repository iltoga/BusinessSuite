from django_unicorn.components import UnicornView
from customers.models import Customer


class CustomerListView(UnicornView):
    customers = []
    search_input = ''
    page = 1
    items_per_page = 7
    start_search_at = 3 # start searching after 3 characters

    def mount(self):
        self.load_customers()

    def load_customers(self):
        self.customers = list(Customer.objects.all()[self.items_per_page*(self.page-1):self.items_per_page*self.page].values())

    def search(self):
        if self.search_input and len(self.search_input) >= self.start_search_at:
            self.customers = list(Customer.objects.search_customers(self.search_input).values())
        else:
            self.load_customers()

    def next_page(self):
        self.page += 1
        self.load_customers()

    def previous_page(self):
        self.page -= 1 if self.page > 1 else 1
        self.load_customers()

