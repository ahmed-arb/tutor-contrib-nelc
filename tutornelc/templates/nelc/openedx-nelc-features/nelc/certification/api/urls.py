"""
URLs for the partner certification API.

Mounted by the platform at ^api/nelc/v1/ via PluginURLs in apps.py, so the
paths here are relative to that.
"""

from django.urls import path

from nelc.certification.api.views import CoachOwnGroupView

app_name = "nelc_certification"

urlpatterns = [
    path("coach/me/group/", CoachOwnGroupView.as_view(), name="coach-own-group"),
]
