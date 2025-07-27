from django.contrib import admin

from products.models import Product, Task, DocumentType
from nested_admin import NestedModelAdmin, NestedStackedInline, NestedTabularInline

class TaskTabularInline(NestedTabularInline):
    model = Task
    extra = 0

@admin.register(Product)
class ProductAdmin(NestedModelAdmin):
    inlines = [TaskTabularInline, ]

admin.site.register(DocumentType)