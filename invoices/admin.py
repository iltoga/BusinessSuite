from django.contrib import admin
from nested_admin import NestedModelAdmin, NestedTabularInline

from payments.models import Payment

from .models import Invoice, InvoiceApplication


class PaymentApplicationTabularInline(NestedTabularInline):
    model = Payment
    extra = 0


class InvoiceApplicationTabularInline(NestedTabularInline):
    model = InvoiceApplication
    extra = 0
    inlines = [PaymentApplicationTabularInline]  # Add PaymentApplicationTabularInline as nested inline here


@admin.register(Invoice)
class InvoiceAdmin(NestedModelAdmin):
    inlines = [InvoiceApplicationTabularInline]


@admin.register(InvoiceApplication)
class InvoiceApplicationAdmin(admin.ModelAdmin):
    model = InvoiceApplication
