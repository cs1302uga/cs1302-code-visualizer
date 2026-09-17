"""Certificate environment setup for browser startup and downloads."""

import os

import certifi


def ensure_certifi_bundle() -> None:
    """Point SSL_CERT_FILE at the installed certifi bundle unless already correct."""
    certificate_bundle = certifi.where()
    if os.environ.get("SSL_CERT_FILE") != certificate_bundle:
        os.environ["SSL_CERT_FILE"] = certificate_bundle
