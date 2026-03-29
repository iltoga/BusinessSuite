"""
FILE_ROLE: Provides template filters and tags for document display and formatting helpers.

KEY_COMPONENTS:
- pretty_json: Formats values as indented JSON for templates.
- endswith: Checks string suffixes in templates.
- slice_after: Returns the string prefix up to a marker.
- get_incomplete_documents: Returns incomplete documents for a DocApplication.
- get_completed_documents: Returns completed documents for a DocApplication.
- as_currency: Formats numeric values as currency.
- as_date_str: Formats values as date strings.
- split: Splits and trims a delimited string.

INTERACTIONS:
- Depends on: core.utils.formatutils, django.template, django.conf.settings, DocApplication methods.

AI_GUIDELINES:
- Keep these helpers presentation-focused and side-effect free.
- Prefer delegating formatting rules to utility functions rather than embedding them in templates.
"""

import json

import core.utils.formatutils as formatutils
from django import template
from django.conf import settings

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


@register.filter
def split(value, key):
    return [item.strip() for item in value.split(key)] if value else []
