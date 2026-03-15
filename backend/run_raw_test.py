import sys
import os

with open("raw_output.txt", "w") as f_out:
    try:
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'business_suite.settings.dev')
        os.environ.setdefault('SECRET_KEY', 'django-insecure-dev-only')
        django.setup()
        
        from core.services.ai_passport_parser import AIPassportParser
        
        f_out.write("Django loaded.\n")
        
        parser = AIPassportParser(model="qwen/qwen3.5-flash-02-23", use_openrouter=True)
        f_out.write("Parser loaded.\n")
        
        with open('tmp/passport.jpeg', 'rb') as f_img:
            img_data = f_img.read()
            
        f_out.write("Calling vision API...\n")
        res = parser._call_vision_api(img_data, 'passport.jpeg', parser._build_vision_prompt())
        
        f_out.write(f"Success: {res.success}\n")
        f_out.write(f"Error: {res.error_message}\n")
    except Exception as e:
        import traceback
        f_out.write(traceback.format_exc())
