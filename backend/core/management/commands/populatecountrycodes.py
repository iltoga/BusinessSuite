import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError

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
        for country in country_data:
            alpha3 = country.get("alpha3_code")
            alpha2 = country.get("alpha2_code")
            numeric = country.get("numeric_code")
            country_name = country.get("country")
            country_idn = country.get("country_idn") or country.get("country_id")

            # Validate alpha3 exists
            if not alpha3:
                print(f"Skipping entry without alpha3_code: {country}")
                continue

            # Check for conflicting alpha2_code or numeric_code used by a different alpha3
            conflicting_alpha2 = (
                CountryCode.objects.filter(alpha2_code=alpha2).exclude(alpha3_code=alpha3).first() if alpha2 else None
            )
            conflicting_numeric = (
                CountryCode.objects.filter(numeric_code=numeric).exclude(alpha3_code=alpha3).first()
                if numeric
                else None
            )
            if conflicting_alpha2:
                print(
                    f"Conflict: alpha2_code {alpha2} already used by {conflicting_alpha2.alpha3_code}; skipping {alpha3}"
                )
                continue
            if conflicting_numeric:
                print(
                    f"Conflict: numeric_code {numeric} already used by {conflicting_numeric.alpha3_code}; skipping {alpha3}"
                )
                continue

            try:
                obj, created = CountryCode.objects.update_or_create(
                    alpha3_code=alpha3,
                    defaults={
                        "country": country_name,
                        "alpha2_code": alpha2,
                        "numeric_code": numeric,
                        "country_idn": country_idn,
                    },
                )
            except IntegrityError as e:
                print(f"IntegrityError creating/updating {alpha3}: {e}; skipping")
                continue
            if created:
                print(f"Created country code for {country_name} ({alpha3})")
            else:
                # Update the existing entry if any of the codes or country_idn have changed
                changed = False
                if obj.alpha2_code != country["alpha2_code"]:
                    obj.alpha2_code = country["alpha2_code"]
                    changed = True
                if obj.alpha3_code != country["alpha3_code"]:
                    obj.alpha3_code = country["alpha3_code"]
                    changed = True
                if obj.numeric_code != country["numeric_code"]:
                    obj.numeric_code = country["numeric_code"]
                    changed = True
                # prefer the newly populated `country_idn` if present
                new_country_idn = country.get("country_idn") or country.get("country_id")
                if new_country_idn and obj.country_idn != new_country_idn:
                    obj.country_idn = new_country_idn
                    changed = True
                if changed:
                    try:
                        obj.save()
                        print(f"Updated country code for {country_name} ({alpha3})")
                    except IntegrityError as e:
                        print(f"IntegrityError when updating {alpha3}: {e}; skipping")
                else:
                    print(f"Country code for {country_name} ({alpha3}) already exists and is up-to-date")
