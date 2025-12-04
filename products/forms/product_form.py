from django import forms

from products.models import DocumentType, Product


class SortableSelectMultiple(forms.SelectMultiple):
    """
    Custom widget that renders a sortable list for multi-select.
    Allows drag-and-drop reordering of selected items.
    Preserves order of initially selected items.
    """

    template_name = "products/widgets/sortable_select_multiple.html"

    def __init__(self, attrs=None, choices=(), ordered_initial=None):
        super().__init__(attrs, choices)
        self.ordered_initial = ordered_initial or []

    class Media:
        css = {"all": []}
        js = []

    def get_context(self, name, value, attrs):
        # IMPORTANT: Pass the ordered_initial as value if no value provided
        # This ensures Django marks options as selected correctly
        if value is None and self.ordered_initial:
            value = self.ordered_initial
        context = super().get_context(name, value, attrs)
        # Add ordered initial values to context for the template
        context["widget"]["ordered_initial"] = self.ordered_initial
        return context


class ProductForm(forms.ModelForm):
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 1}))
    product_type = forms.ChoiceField(choices=Product.PRODUCT_TYPE_CHOICES, initial="visa")
    validity = forms.IntegerField(label="Validity (days)", required=False)
    documents_min_validity = forms.IntegerField(label="Documents min. validity (days)", required=False)

    # Extra form fields - using custom sortable widget
    required_documents_multiselect = forms.ModelMultipleChoiceField(
        queryset=DocumentType.objects.filter(is_in_required_documents=True),
        widget=SortableSelectMultiple(attrs={"class": "sortable-select", "data-field": "required"}),
        required=False,
        label="Required documents",
    )
    optional_documents_multiselect = forms.ModelMultipleChoiceField(
        queryset=DocumentType.objects.filter(is_in_required_documents=False),
        widget=SortableSelectMultiple(attrs={"class": "sortable-select", "data-field": "optional"}),
        required=False,
        label="Optional documents",
    )

    class Meta:
        model = Product
        fields = [
            "name",
            "code",
            "description",
            "immigration_id",
            "base_price",
            "product_type",
            "validity",
            "documents_min_validity",
        ]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super(ProductForm, self).__init__(*args, **kwargs)

        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            # Preserve order from the comma-separated string

            # Required documents - get in order from stored string
            required_doc_names = [
                name.strip() for name in (instance.required_documents or "").split(",") if name.strip()
            ]
            if required_doc_names:
                # Get documents and preserve order
                doc_objects = list(DocumentType.objects.filter(name__in=required_doc_names))
                # Sort by the order in the string
                doc_objects.sort(
                    key=lambda d: required_doc_names.index(d.name) if d.name in required_doc_names else 999
                )
                # Set initial as list of PKs (strings) - this is what the widget expects
                ordered_pks = [str(d.pk) for d in doc_objects]
                self.fields["required_documents_multiselect"].initial = [d.pk for d in doc_objects]
                # Pass ordered PKs to widget for JS initialization
                self.fields["required_documents_multiselect"].widget.ordered_initial = ordered_pks

            # Optional documents - get in order from stored string
            optional_doc_names = [
                name.strip() for name in (instance.optional_documents or "").split(",") if name.strip()
            ]
            if optional_doc_names:
                doc_objects = list(DocumentType.objects.filter(name__in=optional_doc_names))
                doc_objects.sort(
                    key=lambda d: optional_doc_names.index(d.name) if d.name in optional_doc_names else 999
                )
                # Set initial as list of PKs (strings) - this is what the widget expects
                ordered_pks = [str(d.pk) for d in doc_objects]
                self.fields["optional_documents_multiselect"].initial = [d.pk for d in doc_objects]
                # Pass ordered PKs to widget for JS initialization
                self.fields["optional_documents_multiselect"].widget.ordered_initial = ordered_pks
