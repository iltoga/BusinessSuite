from django.contrib import admin

from .models import Customer


class CustomerAdmin(admin.ModelAdmin):
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


admin.site.register(Customer, CustomerAdmin)
