from rapidfuzz import process
from rapidfuzz.fuzz import ratio

from core.models import CountryCode


def check_country_by_code(code) -> CountryCode:
    """Check if the country code exists in the database. If not, find the closest match."""
    # First check if the exact country code exists
    country = CountryCode.objects.filter(alpha3_code=code)
    if country.exists():
        result = country.first()
        if result is not None:
            return result
        else:
            raise ValueError(f"Country code {code} does not exist in the database.")

    # Get all the alpha3_code from the database
    country_codes = [country.alpha3_code for country in CountryCode.objects.all()]

    # Generate OCR error correction variants - handle common misreads
    if code:
        # For IIA -> ITA conversion (I misread as 1, or vice versa)
        variants = set([code])  # Use set to avoid duplicates

        # Generate all possible single-character OCR corrections
        for i, char in enumerate(code):
            # Common OCR misreads
            replacements = {
                "I": ["1", "l", "T"],  # I often misread as 1, l, or T
                "1": ["I", "l"],
                "l": ["I", "1"],
                "O": ["0", "Q"],
                "0": ["O"],
                "Q": ["O"],
                "B": ["8"],
                "8": ["B"],
                "S": ["5"],
                "5": ["S"],
            }

            if char in replacements:
                for replacement in replacements[char]:
                    variant = code[:i] + replacement + code[i + 1 :]
                    variants.add(variant)

        # Check all variants for exact matches first
        for variant in variants:
            if variant in country_codes:
                country = CountryCode.objects.get(alpha3_code=variant)
                print(f"OCR correction: '{code}' -> '{variant}' ({country.country})")
                return country

    # If no exact variant match, use fuzzy matching with higher threshold
    best_match = process.extractOne(code, country_codes, scorer=ratio, score_cutoff=75)
    if best_match is not None:
        country = CountryCode.objects.get(alpha3_code=best_match[0])
        print(f"Fuzzy match: '{code}' -> '{best_match[0]}' ({country.country}) with score {best_match[1]}")
        return country

    raise ValueError(f"Country code {code} does not exist in the database.")
