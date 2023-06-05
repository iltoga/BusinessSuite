from django_unicorn.components import UnicornView
from math import ceil

class UnicornSearchListView(UnicornView):
    list_items = []
    search_input = ''
    page = 1
    items_per_page = 7
    start_search_at = 2
    total_items = 0
    total_pages = 0
    model = None
    model_search_method = ''

    def mount(self):
        self.total_items = self.model.objects.count()
        self.total_pages = ceil(self.total_items / self.items_per_page)
        self.load_items()

    def load_items(self):
        self.list_items = list(self.model.objects.all()[self.items_per_page*(self.page-1):self.items_per_page*self.page])

    def search(self):
        if self.search_input and len(self.search_input) >= self.start_search_at:
            search_func = getattr(self.model.objects, self.model_search_method)
            self.list_items = list(search_func(self.search_input))
            self.total_items = len(self.list_items)
            self.total_pages = ceil(self.total_items / self.items_per_page)
        else:
            self.total_items = self.model.objects.count()
            self.total_pages = ceil(self.total_items / self.items_per_page)
            self.load_items()

    def next_page(self):
        self.page += 1
        self.load_items()

    def previous_page(self):
        self.page -= 1 if self.page > 1 else 1
        self.load_items()

    def has_previous(self):
        return self.page > 1

    def has_next(self):
        return self.page * self.items_per_page < self.total_items
