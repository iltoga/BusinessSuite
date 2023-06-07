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
    query = ''
    order_by = 'id'
    filter_type = 'exclude'
    qry_filter_args = None

    def mount(self):
        self.total_items = self.model.objects.count()
        self.total_pages = ceil(self.total_items / self.items_per_page)
        self.load_items()


    def load_items(self):
        # If we have a query, filter based on that query
        if self.query:
            search_func = getattr(self.model.objects, self.model_search_method)
            queryset = search_func(self.query).order_by(self.order_by)
        else:
            # Otherwise, just get all items
            queryset = self.model.objects.all().order_by(self.order_by)

        # If we want to filter by completion status
        if self.filter_type and self.qry_filter_args and isinstance(self.qry_filter_args, dict):
            if self.filter_type == 'exclude':
                queryset = queryset.exclude(**self.qry_filter_args)
            else:
                queryset = queryset.filter(**self.qry_filter_args)

        start = self.items_per_page*(self.page-1)
        end = self.items_per_page*self.page

        self.list_items = list(queryset[start:end])
        self.total_items = queryset.count()
        self.total_pages = ceil(self.total_items / self.items_per_page)


    def search(self):
        if self.search_input and len(self.search_input) >= self.start_search_at:
            search_func = getattr(self.model.objects, self.model_search_method)
            self.list_items = list(search_func(self.search_input).order_by(self.order_by)[self.items_per_page*(self.page-1):self.items_per_page*self.page])
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
