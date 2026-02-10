from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, class_name):
    return field.as_widget(attrs={"class": class_name})

@register.filter
def boolean_to_yes_no(value):
    return 'Yes' if value else 'No'