from rapidfuzz import process
from rapidfuzz.fuzz import ratio

from core.models import CountryCode


def check_country_by_code(code) -> CountryCode:
    """Check if the country code exists in the database. If not, find the closest match."""
    country = CountryCode.objects.filter(alpha3_code=code)
    if country.exists():
        return country.first()

    # Get all the alpha3_code from the database
    country_codes = [country.alpha3_code for country in CountryCode.objects.all()]

    # Use RapidFuzz to find the closest match
    # Note: it returns a tuple of (best_match, score, choice_idx) or None if no match was found
    best_match = process.extractOne(code, country_codes, scorer=ratio, score_cutoff=60)
    if best_match is not None:
        country = CountryCode.objects.get(alpha3_code=best_match[0])
        return country

    raise ValueError(f"Country code {code} does not exist in the database.")
