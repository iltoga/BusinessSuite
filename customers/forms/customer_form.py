from django import forms

from customers.models import Customer, DOCUMENT_TYPE_CHOICES, TITLES_CHOICES, NOTIFY_BY_CHOICES

class CustomerForm(forms.ModelForm):
    birthdate = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    address_bali = forms.CharField(widget=forms.Textarea(attrs={'rows': 5}), required=False)
    address_abroad = forms.CharField(widget=forms.Textarea(attrs={'rows': 5}), required=False)
    notify_documents_expiration = forms.BooleanField(widget=forms.CheckboxInput, required=False)
    notify_by = forms.ChoiceField(choices=NOTIFY_BY_CHOICES, required=False)

    class Meta:
        model = Customer
        fields = ['full_name', 'email', 'telephone', 'whatsapp', 'telegram', 'title', 'citizenship', 'birthdate',
                  'address_bali', 'address_abroad', 'notify_documents_expiration', 'notify_by']

    # Already implemented in the model. I just wanted to show how to do it in the form class
    # def clean(self):
    #     cleaned_data = super().clean()
    #     if not self.is_valid():
    #         return cleaned_data
    #     notify_documents_expiration = cleaned_data.get('notify_documents_expiration')
    #     notify_by = cleaned_data.get('notify_by')

    #     if notify_documents_expiration and not notify_by:
    #         self.add_error('notify_by', ValidationError('This field is required when "notify expiration" is checked'))

    #     return cleaned_data