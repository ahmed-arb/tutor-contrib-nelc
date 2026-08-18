"""
URLs for the partner certification app.

Mounted at the site root by PluginURLs in apps.py, so every path here is written
out in full. Mounting at the root rather than under a single prefix is deliberate:
the coach API wants a versioned /api/nelc/v1/ path, and the learner's landing page
wants a clean /nelc/dashboard/ one. One namespace covers both.
"""

from django.urls import path

from nelc.certification.api.views import CoachOwnGroupView
from nelc.certification.views import CertificationDashboardView

app_name = "nelc_certification"

urlpatterns = [
    path("api/nelc/v1/coach/me/group/", CoachOwnGroupView.as_view(), name="coach-own-group"),
    path("nelc/dashboard/", CertificationDashboardView.as_view(), name="certification-dashboard"),
]
