import os
import django
from django.db import connection

def verify():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    
    print("========================================")
    try:
        # Check connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            if row and row[0] == 1:
                print("Database connection successful: YES")
            else:
                print("Database connection successful: UNKNOWN")
                
        # List major tables and their row counts
        tables = connection.introspection.table_names()
        print("\n--- Core Table Statistics ---")
        models_to_check = [
            ("authentication.AdminUser", "Admin Users"),
            ("authentication.SystemSettings", "System Settings"),
            ("contacts.UploadedFile", "Uploaded Files"),
            ("contacts.Contact", "Contacts"),
            ("templates_engine.EmailTemplate", "Templates"),
            ("campaigns.Campaign", "Campaigns"),
            ("campaigns.CampaignContact", "Campaign Queue"),
            ("campaigns.EmailLog", "Email Logs")
        ]
        
        from django.apps import apps
        for model_path, display_name in models_to_check:
            try:
                model = apps.get_model(model_path)
                count = model.objects.count()
                print(f"{display_name:<20}: {count} rows")
            except Exception as e:
                print(f"{display_name:<20}: Error ({e})")
                
    except Exception as e:
        print("Database connection failed!")
        print(e)
    print("========================================")

if __name__ == "__main__":
    verify()
