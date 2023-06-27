from math import ceil

from django_unicorn.components import UnicornView


class UnicornSearchListView(UnicornView):
    list_items = []
    search_input = ""
    page = 1
    items_per_page = 10
    start_search_at = 0
    total_items = 0
    total_pages = 0
    model = None
    model_search_method = ""
    query = ""
    order_by = ""
    sort_dir = "asc"
    filter_type = "exclude"
    qry_filter_args = None

    def mount(self):
        self.total_items = self.model.objects.count()
        self.total_pages = ceil(self.total_items / self.items_per_page)
        self.load_items()

    def apply_filters(self, queryset):
        if self.filter_type and self.qry_filter_args and isinstance(self.qry_filter_args, dict):
            if self.filter_type == "exclude":
                return queryset.exclude(**self.qry_filter_args)
            else:
                return queryset.filter(**self.qry_filter_args)
        return queryset

    def load_items(self):
        queryset = self.get_queryset()
        start = self.items_per_page * (self.page - 1)
        end = self.items_per_page * self.page

        self.list_items = list(queryset[start:end])
        # self.list_items = queryset[start:end]
        self.total_items = queryset.count()
        self.total_pages = ceil(self.total_items / self.items_per_page)

    def search(self, clear_input=False):
        if clear_input:
            self.search_input = ""
        if self.search_input and self.search_input != "" and len(self.search_input) >= self.start_search_at:
            self.query = self.search_input
            queryset = self.get_queryset()
            start = self.items_per_page * (self.page - 1)
            end = self.items_per_page * self.page

            self.list_items = list(queryset[start:end])
            # self.list_items = queryset[start:end]
            self.total_items = queryset.count()
            self.total_pages = ceil(self.total_items / self.items_per_page)
        else:
            self.query = None  # Or whatever is appropriate to reset the query
            self.load_items()

    def get_queryset(self):
        if self.query:
            search_func = getattr(self.model.objects, self.model_search_method)
            queryset = search_func(self.query)
        else:
            queryset = self.model.objects.all()

        queryset = self.apply_filters(queryset)

        # Unpack the list when calling order_by
        order = self.get_order()
        queryset = queryset.order_by(*order)

        return queryset

    def get_order(self):
        if self.order_by == "":
            if self.model._meta.ordering is None or len(self.model._meta.ordering) == 0:
                return ["id"]
            return self.model._meta.ordering
        return [self.order_by] if self.sort_dir == "asc" else ["-" + self.order_by]

    def sort(self, column):
        if column == self.order_by:
            self.sort_dir = "desc" if self.sort_dir == "asc" else "asc"
        else:
            self.order_by = column
            self.sort_dir = "asc"
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
