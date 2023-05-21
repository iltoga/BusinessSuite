from django.views.generic import ListView
from customers.models import Customer

class CustomerListView(ListView):
    model = Customer
    paginate_by = 15  # Change this number to the desired items per page
    template_name = 'customers/list_customer.html'  # Assuming your template is in this location
