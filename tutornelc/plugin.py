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

# Runs on `tutor local do init` and on `tutor local launch`. Migrations for a
# Django app installed via plugin are not picked up by the platform's own
# migrate step in a fresh environment, so we run them explicitly and
# idempotently. --limit=nelc runs only this.
hooks.Filters.CLI_DO_INIT_TASKS.add_item(
    (
        "lms",
        """
echo "NELC: applying partner certification migrations..."
./manage.py lms migrate nelc_certification

echo "NELC: seeding demo partner, tiers, coach group and learners..."
./manage.py lms seed_nelc_demo
""",
    )
)


########################################
# TEMPLATE RENDERING
########################################

hooks.Filters.ENV_TEMPLATE_ROOTS.add_items(
    [
        str(importlib_resources.files("tutornelc") / "templates"),
    ]
)

# Note: openedx-nelc-features is deliberately NOT a template target. It is
# plain Python, not Jinja, and Tutor would try to render any {{ }} it contains.
# _sync_django_app copies it verbatim instead.
hooks.Filters.ENV_PATTERNS_IGNORE.add_items([r"(.*/)?openedx-nelc-features(/.*)?"])


########################################
# PATCH LOADING
########################################

for path in glob(str(importlib_resources.files("tutornelc") / "patches" / "*")):
    with open(path, encoding="utf-8") as patch_file:
        hooks.Filters.ENV_PATCHES.add_item((os.path.basename(path), patch_file.read()))
