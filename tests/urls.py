"""
URL root for the standalone checks.

Mirrors the prefix the platform mounts for us via PluginURLs.REGEX in apps.py,
so the paths under test match the paths in production.
"""

from django.urls import include, path

urlpatterns = [
    path("", include("nelc.certification.urls")),
]
