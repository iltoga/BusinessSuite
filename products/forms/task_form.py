from django import forms

from products.models import Product, Task


class TaskForm(forms.ModelForm):
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 1}), required=False)

    class Meta:
        model = Task
        fields = [
            "product",
            "step",
            "last_step",
            "name",
            "description",
            "cost",
            "duration",
            "duration_is_business_days",
            "notify_days_before",
        ]

    # if update a new task, then the product field is disabled
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super(TaskForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["product"].disabled = True
            self.fields["step"].disabled = True


TaskModelFormSet = forms.inlineformset_factory(
    Product,  # parent model
    Task,  # child model
    form=TaskForm,  # form to use
    extra=0,  # minimum number of forms to show
    max_num=10,  # maximum number of forms to show
    can_delete=True,  # enable deletion
)
