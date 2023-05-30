from django.contrib import admin

from .models import Product, Task
from nested_admin import NestedModelAdmin, NestedStackedInline, NestedTabularInline

class TaskTabularInline(NestedTabularInline):
    model = Task
    extra = 0

@admin.register(Product)
class ProductAdmin(NestedModelAdmin):
    inlines = [TaskTabularInline, ]
