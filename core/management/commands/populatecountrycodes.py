import json

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import CountryCode


class Command(BaseCommand):
    help = "Populate CountryCode table"

    def handle(self, *args, **options):
        # open the json file from static folder. the file name is country_codes.json
        # static_root = settings.STATIC_ROOT
        static_root = settings.STATICFILES_DIRS[0]
        try:
            with open(f"{static_root}/country_codes.json", "r") as json_file:
                country_data = json.load(json_file)  # Changed this line
        except FileNotFoundError:
            print("country_codes.json file not found")
            return

        self.populate_country_code(country_data)

    def populate_country_code(self, country_data):
        for country in country_data:  # Changed this line
            if not CountryCode.objects.filter(country=country["country"]).exists():
                CountryCode.objects.create(
                    country=country["country"],
                    alpha2_code=country["alpha2_code"],
                    alpha3_code=country["alpha3_code"],
                    numeric_code=country["numeric_code"],
                )
                print(f"Created country code for {country['country']}")
            else:
                print(f"Country code for {country['country']} already exists")
