import json

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(is_safe=True)
def to_json(value):
    """
    Convert a Python object to JSON for use in JavaScript.
    Usage: {{ my_data|to_json }}
    """
    return mark_safe(json.dumps(value, cls=DjangoJSONEncoder))
