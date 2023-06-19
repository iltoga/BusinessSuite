from rapidfuzz import process

from core.models import CountryCode


def check_country_by_code(code) -> CountryCode:
    """Check if the country code exists in the database. If not, find the closest match."""
    country = CountryCode.objects.filter(alpha3_code=code)
    country_exists = country.exists()
    if country_exists:
        return country.first()

    # Get all the alpha3_code from the database
    country_codes = CountryCode.objects.values_list("alpha3_code", flat=True)

    # Use RapidFuzz to find the closest match
    best_match, score = process.extractOne(code, country_codes)
    if score > 70:
        return CountryCode.objects.get(alpha3_code=best_match)

    raise ValueError(f"Country code {code} does not exist in the database.")
