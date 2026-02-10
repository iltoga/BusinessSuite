def whitespaces_to_underscores(name):
    """Replaces white spaces in a person name with underscores.

    Args:
    name: The person name.

    Returns:
    The person name with white spaces replaced with underscores.
    """

    # Trim whitespaces before and after the name.
    name = name.strip()

    # Replace white spaces with underscores.
    return name.replace(' ', '_')

def underscores_to_whitespaces(name):
    """Replaces underscores in a person name with white spaces.

    Args:
    name: The person name.

    Returns:
    The person name with underscores replaced with white spaces.
    """

    # Trim whitespaces before and after the name.
    name = name.strip()

    # Replace underscores with white spaces.
    return name.replace('_', ' ')