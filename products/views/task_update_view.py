from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView
from products.forms import TaskForm
from products.models import Task

class TaskUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ('products.change_task',)
    model = Task
    form_class = TaskForm
    template_name = 'products/task_update.html'
    success_message = "Task updated successfully!"

    def get_success_url(self):
        return reverse_lazy('product-detail', kwargs={'pk': self.object.product.pk})

