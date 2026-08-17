"""
Plugin settings, loaded into the LMS by the platform's plugin machinery.

Nothing to add yet. The app needs no settings of its own: it mounts its URLs
and connects its receivers through plugin_app in apps.py, and it reuses the
platform's database, auth and DRF configuration. This file exists because
PluginSettings points at it, and because the first real setting (vendor
credentials, rollup staleness threshold) will land here rather than in a Tutor
patch that edits LMS settings globally.
"""


def plugin_settings(settings):  # pylint: disable=unused-argument
    """Inject settings into the LMS. Intentionally empty."""
