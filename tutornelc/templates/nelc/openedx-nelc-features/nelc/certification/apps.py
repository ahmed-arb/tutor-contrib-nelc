"""
Django app config for the partner certification domain.

The ``plugin_app`` dict is what makes this an Open edX Django app plugin rather
than a plain Django app: edx-platform's plugin machinery reads it to mount our
URLs, load our settings and connect our signal receivers, all without a fork.
"""

from django.apps import AppConfig
from edx_django_utils.plugins import PluginSettings, PluginSignals, PluginURLs
from openedx.core.djangoapps.plugins.constants import ProjectType, SettingsType


class CertificationConfig(AppConfig):
    """Configuration for the partner certification app."""

    name = "nelc.certification"
    label = "nelc_certification"
    verbose_name = "Partner Certification"
    default_auto_field = "django.db.models.BigAutoField"

    plugin_app = {
        PluginURLs.CONFIG: {
            ProjectType.LMS: {
                PluginURLs.NAMESPACE: "nelc_certification",
                PluginURLs.APP_NAME: "nelc_certification",
                PluginURLs.REGEX: r"^api/nelc/v1/",
                PluginURLs.RELATIVE_PATH: "api.urls",
            },
        },
        PluginSettings.CONFIG: {
            ProjectType.LMS: {
                SettingsType.COMMON: {PluginSettings.RELATIVE_PATH: "settings.common"},
            },
        },
        # Wiring the enrollment receiver declaratively here, rather than
        # importing it from ready(), means the platform owns the connection and
        # it is visible to anyone reading this file. openedx-events signals are
        # ordinary django.dispatch.Signal subclasses, so PluginSignals connects
        # them like any other. COURSE_ENROLLMENT_CREATED has no meaningful
        # sender, so SENDER_PATH is omitted.
        PluginSignals.CONFIG: {
            ProjectType.LMS: {
                PluginSignals.RELATIVE_PATH: "receivers",
                PluginSignals.RECEIVERS: [
                    {
                        PluginSignals.RECEIVER_FUNC_NAME: "on_course_enrollment_created",
                        PluginSignals.SIGNAL_PATH: (
                            "openedx_events.learning.signals.COURSE_ENROLLMENT_CREATED"
                        ),
                    },
                ],
            },
        },
    }
