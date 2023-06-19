from django.contrib import admin

from .models import CountryCode, Holiday

admin.site.register(Holiday)
admin.site.register(CountryCode)
