"""
FILE_ROLE: Provides template filters for simple form-field rendering helpers.

KEY_COMPONENTS:
- add_class: Adds a CSS class to a form field widget.
- boolean_to_yes_no: Renders booleans as human-readable Yes/No text.

INTERACTIONS:
- Depends on: django.template and form field widget rendering.

AI_GUIDELINES:
- Keep filters tiny, deterministic, and presentation-only.
- Avoid introducing business rules or database access in template tags.
"""

from django import template

register = template.Library()


@register.filter(name="add_class")
def add_class(field, class_name):
    return field.as_widget(attrs={"class": class_name})


@register.filter
def boolean_to_yes_no(value):
    return "Yes" if value else "No"
