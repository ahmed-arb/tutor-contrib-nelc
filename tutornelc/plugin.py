"""
Tutor plugin for the partner certification platform.

Responsibilities, in order of appearance below:

1. Declare plugin settings (``NELC_*``).
2. Copy the vendored Django app into the openedx image build context.
3. Load the patches in ``patches/`` (which install the app and switch it on).
4. Register an init task that migrates the app and seeds demo rows.

The Django app itself lives under ``templates/nelc/openedx-nelc-features/``.
Vendoring it here keeps this exercise to a single repository. In a real
deployment it would be its own versioned repo installed from a pinned tag, the
way tutor-contrib-wikilearn installs openedx-wikilearn-features. See
ARCHITECTURE.md, "What I'd defer or decline".
"""

import os
import shutil
from glob import glob

import click
import importlib_resources
from tutor import hooks

from .__about__ import __version__

########################################
# CONFIGURATION
########################################

hooks.Filters.CONFIG_DEFAULTS.add_items(
    [
        ("NELC_VERSION", __version__),
        # Creates a superuser admin/admin during init so a reviewer can log in and
        # click around immediately. True by default because this repo exists to be
        # reviewed, but it is a trivially guessable superuser: set it to false for
        # anything that is not a throwaway local instance.
        #   tutor config save --set NELC_CREATE_DEMO_ADMIN=false
        ("NELC_CREATE_DEMO_ADMIN", True),
    ]
)


########################################
# VENDORED DJANGO APP SYNC
########################################

# Relative to the Tutor project root. The openedx image build context is
# env/build/openedx/, so anything under env/build/openedx/djangoapp/ can be
# COPYied by the openedx-dockerfile-post-python-requirements patch.
APP_DEST = ("env", "build", "openedx", "djangoapp", "nelc", "openedx-nelc-features")
APP_SRC = ("templates", "nelc", "openedx-nelc-features")


def _sync_django_app(root: str) -> None:
    """
    Mirror the vendored Django app into the openedx image build context.

    This is a delete-then-copy rather than a Tutor template target on purpose.
    ENV_TEMPLATE_TARGETS renders and overwrites, but it never deletes, so a file
    removed from the plugin would linger in the environment forever and get
    baked into the next image. Pattern taken from a prior client program
    implementation I led at Edly/Arbisoft.
    """
    dst = os.path.join(root, *APP_DEST)
    src = str(importlib_resources.files("tutornelc").joinpath(*APP_SRC))
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


@hooks.Actions.PROJECT_ROOT_READY.add()
def _auto_sync_django_app(root: str) -> None:
    """Re-sync on every tutor command, so the image never builds a stale app."""
    _sync_django_app(root)


@click.command(name="nelc-sync-app", help="Sync openedx-nelc-features into the Tutor env.")
@click.pass_context
def nelc_sync_app(context: click.Context) -> None:
    _sync_django_app(context.obj.root)
    click.echo("openedx-nelc-features synced.")


hooks.Filters.CLI_COMMANDS.add_item(nelc_sync_app)


########################################
# INIT TASKS
########################################

# Runs on `tutor local do init` and on `tutor local launch`.
#
# The migrate call is belt and braces, not the primary mechanism. Because the
# app is in INSTALLED_APPS via the lms.djangoapp entry point, the platform's own
# init already applies our migrations; on a fresh launch you can see
# "Applying nelc_certification.0001_initial" in the platform's migrate output,
# and this task then reports nothing to do. It is kept because it makes
# `tutor local do init --limit=nelc` a complete, self-sufficient way to
# (re)initialise just this plugin, which is what you want after upgrading it
# without re-running the whole platform init.
hooks.Filters.CLI_DO_INIT_TASKS.add_item(
    (
        "lms",
        """
echo "NELC: applying partner certification migrations..."
./manage.py lms migrate nelc_certification

echo "NELC: seeding demo partner, tiers, coach group and learners..."
./manage.py lms seed_nelc_demo

# Makes the certification dashboard the learner's landing page. student_dashboard()
# only honours LEARNER_HOME_MICROFRONTEND_URL when this flag is on. Idempotent.
echo "NELC: enabling learner_home_mfe.enabled so /dashboard redirects to us..."
./manage.py lms waffle_flag --create --everyone learner_home_mfe.enabled

{% if NELC_CREATE_DEMO_ADMIN %}
# Demo superuser so a reviewer can sign in without extra steps. Idempotent: the
# password is reset on every init so it is always the documented one.
echo "NELC: creating demo superuser admin/admin..."
./manage.py lms manage_user admin admin@example.com --superuser --staff
./manage.py lms shell -c "
from django.contrib.auth import get_user_model
u = get_user_model().objects.get(username='admin')
u.set_password('admin')
u.save()
print('NELC: admin password set')
"
{% endif %}
""",
    )
)


########################################
# HEADER TAB
########################################

# Adds a Certification tab to the learner-facing header, ahead of the platform's
# own Courses and Discover links, which stay where they are.
#
# The widget is written inline here rather than shipped as an npm package. That is
# possible because a nav tab is just an anchor; frontend-plugin-framework evaluates
# this string inside env.config.jsx, so a plain arrow component needs no build of
# our own. Pattern taken from tutor-indigo-wikilearn.
#
# tutor-mfe is an optional dependency: without it there are no MFEs to inject into,
# and the backend slice still works, so the import is guarded rather than required.
try:
    from tutormfe.hooks import PLUGIN_SLOTS

    CERTIFICATION_TAB = """
            {
              op: PLUGIN_OPERATIONS.Insert,
              widget: {
                id: 'nelc_certification_tab',
                type: DIRECT_PLUGIN,
                priority: 1,
                RenderWidget: () => (
                  <a className="nav-link" href={`${getConfig().LMS_BASE_URL}/nelc/dashboard/`}>
                    Certification
                  </a>
                ),
              },
            }
    """

    for _mfe in ("learner-dashboard", "profile", "account"):
        PLUGIN_SLOTS.add_item(
            (
                _mfe,
                # Slot id as published by @edx/frontend-component-header 8.2.x, which is
                # what the Verawood MFEs pin. Older releases used the short name
                # "desktop_main_menu_slot".
                "org.openedx.frontend.layout.header_desktop_main_menu.v1",
                CERTIFICATION_TAB,
            )
        )
except ImportError:  # pragma: no cover
    # tutor-mfe not installed. Nothing to inject into.
    pass


########################################
# TEMPLATE RENDERING
########################################

hooks.Filters.ENV_TEMPLATE_ROOTS.add_items(
    [
        str(importlib_resources.files("tutornelc") / "templates"),
    ]
)

# No ENV_TEMPLATE_TARGETS are registered, so nothing under templates/ is
# rendered into the Tutor environment, and that is the point.
# openedx-nelc-features is plain Python: Tutor's Jinja pass would try to
# interpret any {{ }} in it, and dict/set literals in Python source are exactly
# the kind of thing that trips that up. _sync_django_app copies it verbatim
# instead. If a real Jinja template is ever added here, give it its own target
# directory rather than widening one to cover the app.


########################################
# PATCH LOADING
########################################

for path in glob(str(importlib_resources.files("tutornelc") / "patches" / "*")):
    with open(path, encoding="utf-8") as patch_file:
        hooks.Filters.ENV_PATCHES.add_item((os.path.basename(path), patch_file.read()))
