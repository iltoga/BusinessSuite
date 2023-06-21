from django.contrib import admin
from nested_admin import NestedModelAdmin, NestedTabularInline

from .models import DocApplication, Document, DocWorkflow


class DocWorkflowTabularInline(NestedTabularInline):
    model = DocWorkflow
    extra = 0


class DocumentTabularInline(NestedTabularInline):
    model = Document
    extra = 0


@admin.register(DocApplication)
class DocApplicationAdmin(NestedModelAdmin):
    inlines = [DocWorkflowTabularInline, DocumentTabularInline]
