from django.core.management.base import BaseCommand
from datetime import date
from core.models import Holiday
from datetime import date

class Command(BaseCommand):
    help = 'Populate holiday table for the next 10 years in Indonesia'

    HOLIDAYS_DATA = {
        2023: {
            'New Year': date(2023, 1, 1),
            'Chinese New Year': date(2023, 1, 22),
            'Isra Mi\'raj': date(2023, 2, 18),
            'Nyepi': date(2023, 3, 22),
            'Good Friday': date(2023, 4, 7),
            'Idul Fitri': date(2023, 4, 22),
            'Ascension of Jesus Christ': date(2023, 5, 18),
            'Pancasila Day': date(2023, 6, 1),
            'Waisak Day': date(2023, 6, 4),
            'Idul Adha': date(2023, 6, 29),
            'Islamic New Year': date(2023, 7, 19),
            'Independence Day': date(2023, 8, 17),
            'Maulid Nabi Muhammad SAW': date(2023, 9, 28),
            'Christmas': date(2023, 12, 25)
        },
        2024: {
            'New Year': date(2024, 1, 1),
            'Isra Mi\'raj': date(2024, 2, 8),
            'Chinese New Year': date(2024, 2, 10),
            'Nyepi': date(2024, 3, 11),
            'Good Friday': date(2024, 3, 29),
            'Idul Fitri': date(2024, 4, 10),
            'Labor Day': date(2024, 5, 1),
            'Ascension of Jesus Christ': date(2024, 5, 9),
            'Waisak Day': date(2024, 5, 23),
            'Pancasila Day': date(2024, 6, 1),
            'Idul Adha': date(2024, 6, 17),
            'Islamic New Year': date(2024, 7, 7),
            'Independence Day': date(2024, 8, 17),
            'Maulid Nabi Muhammad SAW': date(2024, 9, 15),
            'Christmas': date(2024, 12, 25)
        },
        2025: {
            'New Year': date(2025, 1, 1),
            'Isra Mi\'raj': date(2025, 1, 27),
            'Chinese New Year': date(2025, 1, 29),
            'Nyepi': date(2025, 3, 29),
            'Idul Fitri': date(2025, 3, 31),
            'Good Friday': date(2025, 4, 18),
            'Labor Day': date(2025, 5, 1),
            'Waisak Day': date(2025, 5, 12),
            'Ascension of Jesus Christ': date(2025, 5, 29),
            'Pancasila Day': date(2025, 6, 1),
            'Idul Adha': date(2025, 6, 7),
            'Islamic New Year': date(2025, 6, 27),
            'Independence Day': date(2025, 8, 17),
            'Maulid Nabi Muhammad SAW': date(2025, 9, 5),
            'Christmas': date(2025, 12, 25)
        },
        2026: {
            'New Year': date(2026, 1, 1),
            'Isra Mi\'raj': date(2026, 1, 16),
            'Chinese New Year': date(2026, 2, 17),
            'Nyepi': date(2026, 3, 19),
            'Idul Fitri': date(2026, 3, 20),
            'Good Friday': date(2026, 4, 3),
            'Labor Day': date(2026, 5, 1),
            'Ascension of Jesus Christ': date(2026, 5, 14),
            'Idul Adha': date(2026, 5, 27),
            'Waisak Day': date(2026, 5, 31),
            'Pancasila Day': date(2026, 6, 1),
            'Islamic New Year': date(2026, 6, 17),
            'Independence Day': date(2026, 8, 17),
            'Maulid Nabi Muhammad SAW': date(2026, 8, 25),
            'Christmas': date(2026, 12, 25)
        }
    }

    def handle(self, *args, **options):
        self.populate_holiday()

    def populate_holiday(self):
        self.generate_holiday()

    def generate_holiday(self, silent=False):
        for year in range(2023, 2026):
            self.generate_holiday_for_year(year)

    def generate_holiday_for_year(self, year, country='ID', silent=False):
        holiday_data = self.HOLIDAYS_DATA.get(year)

        if not holiday_data:
            if not silent:
                print(f"No holiday data for the year {year}")
            return

        for holiday_name, holiday_date in holiday_data.items():
            # chack if holiday already exists
            if Holiday.objects.filter(name=holiday_name, date=holiday_date, country=country).exists():
                if not silent:
                    print(f"Holiday {holiday_name} for the date {holiday_date} already exists")
                continue

            holiday, created = Holiday.objects.get_or_create(
                name=holiday_name,
                date=holiday_date,
                country=country,
            )

            if not silent:
                if created:
                    print(f"Created holiday {holiday_name} for the date {holiday_date}")
                else:
                    print(f"Holiday {holiday_name} for the date {holiday_date} already exists")

        # generate all weekends for the year
        for month in range(1, 13):
            for day in range(1, 32):
                # skip if the date is in holiday data
                try:
                    cur_date = date(year, month, day)
                except ValueError:
                    continue

                if cur_date in holiday_data.values():
                    continue

                if cur_date.weekday() in [5, 6]:
                    if not Holiday.objects.filter(date=cur_date, country=country).exists():
                        Holiday.objects.get_or_create(
                            name=cur_date.strftime("%A"),
                            date=cur_date,
                            country=country,
                            is_weekend=True,
                        )

