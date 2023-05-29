from django.contrib import admin
from django.contrib.auth.models import User, Group

class CustomAdminSite(admin.AdminSite):

    def has_permission(self, request):
        # Check if the user is part of the 'Editors' group
        group = Group.objects.get(name='Editors')
        user = User.objects.get(id=request.user.id)
        if group in user.groups.all():
            return True
        # If user is not in 'Editors' group, return the original permission check
        return super().has_permission(request)

# Then instantiate and use your AdminSite
custom_admin_site = CustomAdminSite(name='custom_admin')

# Example of registering a model to this admin site
# my_admin_site.register(MyModel, MyModelAdmin)
