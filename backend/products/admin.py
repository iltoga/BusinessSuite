from django.contrib import admin
from nested_admin import NestedModelAdmin, NestedTabularInline

from products.models import DocumentType, Product, Task


class TaskTabularInline(NestedTabularInline):
    model = Task
    extra = 0


class ProductAdmin(NestedModelAdmin):
    inlines = [TaskTabularInline]

    def delete_model(self, request, obj):
        can_delete, msg = obj.can_be_deleted()
        if not can_delete:
            from django.contrib import messages

            self.message_user(request, msg, messages.ERROR)
            return
        if msg:
            from django.contrib import messages

            self.message_user(request, msg, messages.WARNING)
        super().delete_model(request, obj)


admin.site.register(Product, ProductAdmin)
admin.site.register(DocumentType)
