import json

from django import template

register = template.Library()


@register.filter()
def pretty_json(value):
    return json.dumps(value, indent=4)


@register.filter
def endswith(value, arg):
    """Returns True if the value ends with the arg"""
    return str(value).endswith(str(arg))
