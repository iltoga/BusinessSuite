from django import forms
from django.forms import formset_factory
from django.utils import timezone

from customer_applications.models import DocApplication
from products.models import Product


class CustomerApplicationInlineForm(forms.ModelForm):
    """Form for creating a new customer application inline within invoice creation."""

    class Meta:
        model = DocApplication
        fields = ["product", "doc_date", "notes"]
        widgets = {
            "doc_date": forms.DateInput(attrs={"type": "date", "value": timezone.now().strftime("%Y-%m-%d")}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Person-specific details (names, IDs, etc.)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Just add select2 class
        self.fields["product"].widget.attrs.update({"class": "select2"})
        self.fields["product"].queryset = Product.objects.all()


# Create a formset for multiple new customer applications
CustomerApplicationInlineFormSet = formset_factory(
    CustomerApplicationInlineForm,
    extra=0,  # Start with 0, add dynamically via JS
    can_delete=True,
    max_num=10,  # Reasonable limit
)
