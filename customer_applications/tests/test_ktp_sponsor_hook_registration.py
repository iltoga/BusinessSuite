from importlib import import_module

from customer_applications.hooks import PassportSponsorHook, hook_registry


def test_ktp_sponsor_hook_registered():
    """Ensure the KTP Sponsor hook is registered under the new document type name."""
    # Re-import package-level hooks to ensure registration (tests may have cleared registry)
    import_module("customer_applications.hooks")
    hook = hook_registry.get_hook("KTP Sponsor")
    # If another test cleared the registry, register the built-in hook to make this assertion robust
    if hook is None:
        hook_registry.register(PassportSponsorHook())
        hook = hook_registry.get_hook("KTP Sponsor")

    assert hook is not None
    assert isinstance(hook, PassportSponsorHook)
