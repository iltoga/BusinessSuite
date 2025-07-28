from django.contrib import admin
from nested_admin import NestedModelAdmin, NestedTabularInline

from .models import DocApplication, Document, DocWorkflow


class DocWorkflowTabularInline(NestedTabularInline):
    model = DocWorkflow
    extra = 0


class DocumentTabularInline(NestedTabularInline):
    model = Document
    extra = 0


class DocApplicationAdmin(NestedModelAdmin):
    inlines = [DocWorkflowTabularInline, DocumentTabularInline]

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


admin.site.register(DocApplication, DocApplicationAdmin)
