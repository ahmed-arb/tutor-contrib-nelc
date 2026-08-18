"""Django settings for the standalone checks."""

SECRET_KEY = "not-a-secret-this-is-a-test-harness"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    # The real AppConfig, imported unmodified. The stubs on sys.path let its
    # plugin_app dict be constructed exactly as it is in production.
    "nelc.certification.apps.CertificationConfig",
]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

ROOT_URLCONF = "tests.urls"
USE_TZ = True
