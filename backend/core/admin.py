from django.contrib import admin

from .models import CountryCode, Holiday, UserSettings

admin.site.register(Holiday)
admin.site.register(CountryCode)
admin.site.register(UserSettings)
