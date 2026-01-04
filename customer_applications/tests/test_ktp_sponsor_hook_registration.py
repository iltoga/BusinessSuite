from customer_applications.hooks import PassportSponsorHook, hook_registry


def test_ktp_sponsor_hook_registered():
    """Ensure the KTP Sponsor hook is registered under the new document type name."""
    hook = hook_registry.get_hook("KTP Sponsor")
    assert hook is not None
    assert isinstance(hook, PassportSponsorHook)
