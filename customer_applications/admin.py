from django.contrib import admin
from .models import DocWorkflow, DocApplication, RequiredDocument
from nested_admin import NestedModelAdmin, NestedTabularInline, NestedTabularInline

class DocWorkflowTabularInline(NestedTabularInline):
    model = DocWorkflow
    extra = 0

class RequiredDocumentTabularInline(NestedTabularInline):
    model = RequiredDocument
    extra = 0

@admin.register(DocApplication)
class DocApplicationAdmin(NestedModelAdmin):
    inlines = [DocWorkflowTabularInline, RequiredDocumentTabularInline, ]


