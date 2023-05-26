from django.contrib import admin
from .models import DocWorkflow, DocApplication, RequiredDocument
from nested_admin import NestedModelAdmin, NestedTabularInline, NestedTabularInline
from .forms import DocApplicationForm

class DocWorkflowTabularInline(NestedTabularInline):
    model = DocWorkflow
    extra = 0

# @admin.register(DocApplication)
# class DocApplicationAdmin(NestedModelAdmin):
#     inlines = [DocWorkflowTabularInline, ]
#     list_display = [field.name for field in DocApplication._meta.fields if field.name != "id"]
#     list_display.append('display_required_documents')
#     form = DocApplicationForm

#     def display_required_documents(self, obj):
#         return ", ".join([doc.name for doc in obj.required_documents.all()])
#     display_required_documents.short_description = 'Required Documents'

#     def get_form(self, request, obj=None, **kwargs):
#         form = super().get_form(request, obj, **kwargs)
#         if obj:
#             form.base_fields['required_documents'].queryset = obj.product.required_documents.all()
#         return form

@admin.register(DocApplication)
class DocApplicationAdmin(admin.ModelAdmin):
    form = DocApplicationForm
