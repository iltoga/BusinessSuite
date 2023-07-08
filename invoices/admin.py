from django.contrib import admin
from nested_admin import NestedModelAdmin, NestedTabularInline

from .models import Invoice, InvoiceApplication


class InvoiceApplicationTabularInline(NestedTabularInline):
    model = InvoiceApplication
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(NestedModelAdmin):
    inlines = [InvoiceApplicationTabularInline]
