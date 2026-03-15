import sys
import os

with open("service_output.txt", "w") as f_out:
    try:
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_suite.settings.dev')
        os.environ.setdefault('SECRET_KEY', 'django-insecure-dev-only')
        django.setup()
        
        from core.services.passport_uploadability_service import PassportUploadabilityService
        
        f_out.write("Django loaded.\n")
        
        with open('tmp/passport.jpeg', 'rb') as f_img:
            img_data = f_img.read()
            
        f_out.write("Running service...\n")
        service = PassportUploadabilityService()
        res = service.check_passport(img_data, method="hybrid")
        
        f_out.write(f"Success: {res.is_valid}\n")
        f_out.write(f"Method: {res.method_used}\n")
    except Exception as e:
        import traceback
        f_out.write(traceback.format_exc())
