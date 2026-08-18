"""
The learner's landing page.

Stakeholder request 1 asks for the certification dashboard to be the learner's
landing page instead of the platform default. This is the placeholder that proves
the mechanism: it is genuinely what a learner lands on after login, and it says
plainly that the real dashboard is not built yet.

Why a Django page and not an MFE route: the point being proved here is the
redirect and the header tab, both of which are configuration this Tutor plugin
owns. A real implementation would render this inside the learner dashboard MFE so
it shares the shell chrome. See ARCHITECTURE.md.
"""

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.utils.html import escape
from django.views import View

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Certification dashboard</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; color: #1c1c1c; background: #fff; }}
    nav {{ display: flex; gap: 1.5rem; padding: 1rem 2rem; border-bottom: 1px solid #d7d7d7;
           background: #f7f7f7; }}
    nav a {{ text-decoration: none; color: #00688d; font-weight: 500; }}
    nav a[aria-current="page"] {{ color: #1c1c1c; border-bottom: 2px solid #00688d;
                                  padding-bottom: 2px; }}
    nav span.disabled {{ color: #767676; cursor: help; }}
    main {{ max-width: 44rem; padding: 3rem 2rem; }}
    .stub {{ border: 1px dashed #9c9c9c; border-radius: 6px; padding: 2rem; background: #fbfbfb; }}
    code {{ background: #eee; padding: 0.1rem 0.3rem; border-radius: 3px; }}
    p.meta {{ color: #5c5c5c; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <nav>
    <a href="/nelc/dashboard/" aria-current="page">Certification</a>
    {courses_link}
    <a href="/courses">Discover new</a>
  </nav>
  <main>
    <h1>Certification dashboard</h1>
    <div class="stub">
      <p><strong>The certification dashboard would be displayed here.</strong></p>
      <p class="meta">
        Not built in this slice. It would show the learner's tier, their distance from the
        certification standard on each track they have joined, and their coach.
      </p>
    </div>
    <p class="meta">
      You are seeing this page because <code>LEARNER_HOME_MICROFRONTEND_URL</code> points at it and
      the <code>learner_home_mfe.enabled</code> waffle flag is on, so <code>/dashboard</code>
      redirects here. Both are set by this Tutor plugin. No fork, no core change.
    </p>
  </main>
</body>
</html>
"""


class CertificationDashboardView(LoginRequiredMixin, View):
    """
    Placeholder landing page for a learner's certification dashboard.

    Login required, matching the platform dashboard this replaces: an anonymous
    visitor is sent to the login page rather than shown an empty shell.
    """

    def get(self, request):
        # Link to the real learner dashboard when something else configured one,
        # captured before we took the setting over. Without it, linking to
        # /dashboard would bounce straight back here.
        original = getattr(settings, "NELC_ORIGINAL_LEARNER_HOME_URL", None)
        if original:
            courses_link = f'<a href="{escape(original)}">Courses</a>'
        else:
            # Nothing configured a learner dashboard, which is the case when the
            # mfe plugin is not enabled. Show the tab in its intended position but
            # do not link it anywhere, rather than silently dropping it or linking
            # to /dashboard, which now redirects back to this page.
            courses_link = (
                '<span class="disabled" title="Enable the mfe plugin to get the '
                'learner dashboard MFE">Courses</span>'
            )
        return HttpResponse(PAGE.format(courses_link=courses_link))
