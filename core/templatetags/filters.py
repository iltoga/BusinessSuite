import json

from django import template
from django.conf import settings

import core.utils.formatutils as formatutils

register = template.Library()


@register.filter()
def pretty_json(value):
    return json.dumps(value, indent=4)


@register.filter
def endswith(value, arg):
    """Returns True if the value ends with the arg"""
    return str(value).endswith(str(arg))


@register.filter
def slice_after(value, arg):
    try:
        position = value.index(arg) + len(arg)
        return value[:position]
    except ValueError:
        return value


@register.simple_tag
def get_incomplete_documents(docapplication, doc_type):
    return docapplication.get_incomplete_documents(doc_type)


@register.simple_tag
def get_completed_documents(docapplication, doc_type):
    return docapplication.get_completed_documents(doc_type)


@register.filter(is_safe=True)
def as_currency(value):
    return formatutils.as_currency(value)


@register.filter(is_safe=True)
def as_date_str(value):
    return formatutils.as_date_str(value)
