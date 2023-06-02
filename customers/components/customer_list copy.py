from django_unicorn.components import UnicornView
from customers.models import Customer
from math import ceil

class CustomerListView(UnicornView):
    customers = []
    search_input = ''
    page = 1
    items_per_page = 7
    start_search_at = 3
    total_customers = 0
    total_pages = 0

    def mount(self):
        self.total_customers = Customer.objects.count()
        self.total_pages = ceil(self.total_customers / self.items_per_page)
        self.load_customers()

    def load_customers(self):
        self.customers = list(Customer.objects.all()[self.items_per_page*(self.page-1):self.items_per_page*self.page].values())

    def search(self):
        if self.search_input and len(self.search_input) >= self.start_search_at:
            self.customers = list(Customer.objects.search_customers(self.search_input).values())
            self.total_customers = len(self.customers)
            self.total_pages = ceil(self.total_customers / self.items_per_page)
        else:
            self.total_customers = Customer.objects.count()
            self.total_pages = ceil(self.total_customers / self.items_per_page)
            self.load_customers()

    def next_page(self):
        self.page += 1
        self.load_customers()

    def previous_page(self):
        self.page -= 1 if self.page > 1 else 1
        self.load_customers()

    def has_previous(self):
        return self.page > 1

    def has_next(self):
        return self.page * self.items_per_page < self.total_customers
