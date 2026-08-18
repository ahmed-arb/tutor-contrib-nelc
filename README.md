# tutor-contrib-nelc

A Tutor plugin that installs a partner certification Django app into the Open edX LMS.

This is the working slice for an architecture challenge. The reasoning behind it is in
[ARCHITECTURE.md](ARCHITECTURE.md); the data model is in [docs/erd.md](docs/erd.md).
Read the note first if you want to know why the slice stops where it does.

## What it contains

- **Five models**: `PartnerCompany`, `Tier`, `CoachGroup`, `LearnerRecord`, `LearnerActivity`.
- **One authenticated endpoint**: `GET /api/nelc/v1/coach/me/group/`, which returns the
  requesting coach's own group and refuses to expose anyone else's.
- **The learner's landing page**: `GET /nelc/dashboard/`, a placeholder certification dashboard
  with a Certification tab ahead of the platform's Courses and Discover. `/dashboard` redirects
  here, via a settings patch plus a waffle flag this plugin sets. No fork and no core change.
- **One enrollment-reactive receiver**: on [openedx-events](https://github.com/openedx/openedx-events) `COURSE_ENROLLMENT_CREATED`,
  writes a `LearnerActivity` row for the enrolling learner.

Nothing extra is installed for the offline-grading recommendation in the note:
[`staff-graded-xblock`](https://github.com/openedx/staff-graded-xblock) is already pinned in
Verawood's `requirements/edx/base.txt` at `4.0.0`, so the image ships it and `staffgradedxblock` is
a registered `xblock.v1` entry point out of the box. A course author enables it per course by
adding `staffgradedxblock` to the Advanced Module List in Studio. Nothing in the slice uses it yet.

Not here, on purpose: the public catalogue, the vendor integration, and the track and
certification-standard tables. Those are argued in the note.

Frontend work is mostly out of scope too, with one exception. The brief excludes it, but
stakeholder request 1 is about *where a learner lands*, which is a routing and configuration
question rather than a UI one, so the landing page and its header tab are here. What is behind
that route is a placeholder, not a dashboard.

## Before you run

| Assumption | Value |
| --- | --- |
| Open edX release | Verawood (`OPENEDX_COMMON_VERSION` resolves to `release/verawood.1`) |
| Tutor | Any v22.x. Nothing pins a version by hand; see below |
| Python | 3.10+ on the host, which Tutor v22 requires |
| Docker | Running, with roughly 8 GB available to it |
| Other Tutor plugins | `mfe`, installed and enabled by `make setup`. Needed for the header tab; nothing else in the slice depends on it |

**You will need one `tutor images build openedx mfe`, which takes 15 to 30 minutes.** There is
no way around it and I did not want to fake one: installing a Django app into the LMS means
the app has to be in the image. That is how this would ship to production, and the brief
asked to be shown the production path rather than a shortcut. Everything after the build is
fast.

The plugin does not fork or patch [`edx-platform`](https://github.com/openedx/edx-platform). The app registers itself through the
`lms.djangoapp` entry point, which edx-platform reads at startup to extend `INSTALLED_APPS`,
mount URLs, load settings and connect signal receivers. There is no settings patch for any
of that.

## Bring it up on a clean instance

```bash
git clone https://github.com/ahmed-arb/tutor-contrib-nelc.git
cd tutor-contrib-nelc

python3 -m venv .venv
source .venv/bin/activate
export TUTOR_ROOT="$PWD/tutor-root"

make setup                          # installs and configures Tutor, tutor-mfe and this plugin
tutor images build openedx mfe      # 15 to 30 minutes, and unavoidable
tutor local launch
```

Then open **http://local.openedx.io** and sign in as **`admin` / `admin`**.

### Why those three lines are yours and not the Makefile's

A Makefile cannot set your shell's environment: every recipe line runs in its own subshell, so a
venv it creates and activates is gone by the time you type the next command. Rather than half-do
it, `make setup` installs into whatever venv is active and configures whatever `TUTOR_ROOT` is
exported, and **refuses to run if either is missing**, printing the line you need. That way your
shell and the Makefile cannot disagree about which Python or which instance they mean.

### Where the versions come from

No version number is written down twice. `pyproject.toml` declares
`tutor>=22.0.0,<23.0.0` as this plugin's own dependency, so `pip install -e .` installs a
compatible Tutor and a CI job running the same command gets the same answer. `tutor-mfe` is not
pinned here at all: `tutor plugins install mfe` reads the release-specific plugin index, which for
Verawood carries `src: tutor-mfe>=22.0.0,<23.0.0`, so upstream decides what is compatible instead
of this repo guessing and going stale. On a clean venv that currently resolves to Tutor 22.0.1 and
tutor-mfe 22.0.0.

`TUTOR_ROOT` is worth setting deliberately. If you are reviewing several submissions, each needs
its own root, or they share a config file, a MySQL database and a set of Docker volumes. One note
though: separate roots do not give separate ports. Every Tutor instance wants `local.openedx.io`
on port 80, so run one at a time and `tutor local stop` before switching.

The image build is unavoidable: installing a Django app into the LMS means the app has to be in
the image. That is the production path, and the brief asked to be shown it rather than a shortcut.

### Other commands

| Command | What it does |
| --- | --- |
| `make checks` | The standalone checks in their own venv, no Docker needed |
| `make help` | List every target |
| `tutor local stop` | Stop the platform, needed before starting another submission |
| `tutor local dc down -v` | Stop it and drop the volumes |

### The demo admin

`tutor local launch` creates a superuser **`admin` / `admin`** through this plugin's init task, so
you can sign in and click around without extra steps. That is a deliberately trivial credential on
a throwaway instance, so it sits behind a config flag rather than being unconditional: this plugin
should not quietly create a guessable superuser wherever it is installed.

```bash
tutor config save --set NELC_CREATE_DEMO_ADMIN=false
```

Worth knowing: `admin` lands on the certification dashboard too, because the redirect applies to
every user, not just learners.


### What the seed creates

`seed_nelc_demo` runs as part of init and is idempotent. It creates **two** partner
companies deliberately, because group isolation is not observable with one:

| Partner | Coach | Learners |
| --- | --- | --- |
| `northwind` (Northwind Integrations) | `coach_north` | `learner_north_1` (associate), `learner_north_2` (professional), `learner_north_3` (no tier) |
| `southwind` (Southwind Consulting) | `coach_south` | `learner_south_1` (expert), `learner_south_2` (associate) |

Tiers are `associate` (rank 10), `professional` (20), `expert` (30). Every seeded user has
the password `nelc-demo-password`.

## Hit the endpoint with an authenticated request

The endpoint accepts JWT, bearer and session authentication. JWT via the password grant is
the least fiddly to drive from a terminal.

```bash
# 1. One-off: create an OAuth application that can issue tokens for a user.
tutor local run lms ./manage.py lms create_dot_application \
  --grant-type password --public --skip-authorization \
  --client-id nelc-demo-client \
  nelc-demo coach_north

# 2. Get a JWT for the coach.
TOKEN=$(curl -s -X POST http://local.openedx.io/oauth2/access_token \
  -d client_id=nelc-demo-client \
  -d grant_type=password \
  -d username=coach_north \
  -d password=nelc-demo-password \
  -d token_type=jwt | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

# 3. Call it.
curl -s -H "Authorization: JWT $TOKEN" \
  http://local.openedx.io/api/nelc/v1/coach/me/group/ | python3 -m json.tool
```

Expected shape:

```json
{
  "count": 1,
  "groups": [
    {
      "id": 1,
      "name": "Northwind Cohort A",
      "partner": "northwind",
      "partner_name": "Northwind Integrations",
      "member_count": 3,
      "members": [
        {"id": 1, "username": "learner_north_1", "email": "learner_north_1@example.com",
         "tier": "associate", "tier_rank": 10}
      ]
    }
  ]
}
```

### Check the isolation claim

This is the part worth actually testing. Repeat steps 1 to 3 for `coach_south` and confirm
you get Southwind's two learners and none of Northwind's three. The endpoint takes no group
identifier, so there is no parameter to tamper with; the guarantee is structural rather
than a permission check that could be skipped. A coach who coaches nobody gets
`{"count": 0, "groups": []}` and a 200, not a 403.

## Check the enrollment receiver fires

You need a course to enroll into. A fresh instance has none, so import the demo course first:

```bash
tutor local do importdemocourse
```

Then enroll a seeded learner through the platform's own enrollment path and confirm a
`LearnerActivity` row appears:

```bash
tutor local exec -T lms ./manage.py lms shell <<'EOF'
from django.contrib.auth import get_user_model
from opaque_keys.edx.keys import CourseKey
from common.djangoapps.student.models import CourseEnrollment
from nelc.certification.models import LearnerActivity

User = get_user_model()
course = CourseKey.from_string("course-v1:OpenedX+DemoX+DemoCourse")
CourseEnrollment.enroll(User.objects.get(username="learner_north_1"), course)

for a in LearnerActivity.objects.select_related("learner_record__user"):
    print(a.occurred_at, a.learner_record.user.username, a.event_type, a.course_key, a.context)
EOF
```

`CourseEnrollment.enroll` is the same call the enrollment API and the instructor dashboard make,
so this exercises the real signal rather than a synthetic one. Expect one line, and an INFO log
line reading `[nelc] recorded enrollment activity: learner_record=1 course=...` in
`tutor local logs -f lms`.

The receiver no-ops for anyone without a `LearnerRecord`, which is most users on any real
platform and is not an error. To see that, enroll a user who has no learner record and confirm
the enrollment succeeds while no new `LearnerActivity` row appears.

## Check the claims without building anything

If you would rather not wait 20 minutes to see whether the scoping actually holds, there is a
standalone harness that runs the real models, views, serializers, `apps.py` and receiver with
only the platform-side imports stubbed. It needs no Docker and no [`edx-platform`](https://github.com/openedx/edx-platform):

```bash
# A second venv on purpose: these deps are not in the Tutor one, and the harness
# should not be able to accidentally import anything Tutor pulled in.
deactivate 2>/dev/null || true
python3 -m venv .venv-tests
source .venv-tests/bin/activate
pip install "django>=4.2" djangorestframework django-model-utils
python tests/run_checks.py
```

19 checks covering coach scoping, cross-partner contamination, the tier gate and the receiver's
behaviour. It deliberately does **not** claim to prove the two things only a real instance can
show: that the receiver is genuinely connected to `COURSE_ENROLLMENT_CREATED`, and that the app
loads through the `lms.djangoapp` entry point. Use the two sections above for those.

The interesting case is `mis-assigned learner is withheld from the response`, which writes a
cross-partner `coach_group` with `.update()` to bypass `clean()`, the way a bulk import or a
manual data fix would, and confirms the endpoint still refuses to return that learner.

## Poke at it in the admin

`http://local.openedx.io/admin/nelc_certification/` exposes all five models, so you can
create a partner, tier, coach group and learner record by hand and watch the endpoint
change without a frontend. `LearnerActivity` is read-only and undeletable there, because it
is an append-only audit table.

## What was actually verified, and what was not

Every row below was checked on a **clean instance**: an empty `TUTOR_ROOT/data`, a stock
`tutor images build openedx`, and `tutor local launch`, with Tutor 22.0.1 and
`OPENEDX_COMMON_VERSION=release/verawood.1`. Nothing here was verified by patching a running
container.

| Claim | Result |
| --- | --- |
| App loads via the `lms.djangoapp` entry point | `apps.get_app_config('nelc_certification')` resolves to `nelc.certification` |
| URLs mount under the plugin namespace | `reverse('nelc_certification:coach-own-group')` returns `/api/nelc/v1/coach/me/group/` |
| Migration applies | `Applying nelc_certification.0001_initial... OK` during the platform's own migrate |
| Migration matches the models | `makemigrations --check` reports no changes detected |
| Seed runs from the baked image | 2 partners, 3 tiers, 2 coach groups, 5 learners, 0 activity |
| Seeded users are actually usable | All 5 have a `UserProfile`, without which they cannot be enrolled |
| Receiver is connected | `COURSE_ENROLLMENT_CREATED.receivers` contains `nelc.certification.receivers.on_course_enrollment_created` |
| Receiver fires on a real enrollment | `CourseEnrollment.enroll` produced one `LearnerActivity` row for the tracked learner, carrying the event's own timestamp, course key and mode |
| Receiver no-ops for untracked users | An untracked user enrolled successfully and produced no row |
| Endpoint returns the coach's own group over HTTP+JWT | `coach_north` got its 3 Northwind learners, `coach_south` its 2 Southwind learners |
| Coaches cannot see each other's learners | No overlap between the two responses |
| A learner with no tier serialises cleanly | `learner_north_3` returns `tier: null`, `tier_rank: null` |
| Unauthenticated access is refused | `HTTP 401` |
| `/dashboard` lands the learner on the certification dashboard | `302` to `/nelc/dashboard/`, which returns `200` |
| The landing page requires login | anonymous gets `302` to `/login?next=/nelc/dashboard/` |
| The landing page's own tabs are in the requested order | Certification (current), Courses, Discover new |

**Not yet verified: the header tab in the MFE.** Confirmed so far: the slot config generates into
`env.config.jsx`, the widget compiles into the served learner-dashboard bundle, and the slot id
matches the `@edx/frontend-component-header` 8.2.1 that Verawood pins. Not confirmed: that it
mounts and appears in the header. Two bugs were found by looking at it in a browser, which is why
this row is honest rather than green:

- `getConfig` is not in scope in `env.config.jsx`, so the widget threw a `ReferenceError` and the
  header's error boundary showed "An unexpected error occurred" with no tab. Fixed by importing it
  at the `mfe-env-config-runtime-definitions` hook, which needs `tutor images build mfe` again
  because that file is compiled in by webpack.
- Caddy serves an empty `200` for `apps.local.openedx.io` until it is restarted after `mfe` is
  enabled, because the host block is new to its config. **If MFEs come up blank, run
  `tutor local restart caddy`.** This is the likeliest thing to trip you up on a first run.

To check the tab: sign in at http://local.openedx.io as `admin` / `admin`, then open
http://apps.local.openedx.io/learner-dashboard/ directly. `/dashboard` will not get you there,
since this plugin redirects it. The main menu should read Certification, then Courses and Discover.
If Certification is missing, suspect the slot id first: older releases used the short name
`desktop_main_menu_slot`, and it is a one-line change in `tutornelc/plugin.py`.

Also not verified: Kubernetes, anything under load, and the two-second coach view, which is a claim
about a `LearnerTrackSummary` table this slice does not build. The performance argument in the note
is reasoning, not a measurement.

## Tearing it down

```bash
tutor local stop
tutor local dc down -v   # also drops the volumes
```

## Repository layout

```
tutor-contrib-nelc/
├── ARCHITECTURE.md              the two-page note
├── docs/erd.md                  data model, ours and the platform's
├── docs/implementation-plan.md  what is not built, in the order I would build it
├── docs/diagrams.md             context and coach-view request path
├── tests/run_checks.py          standalone checks, no Docker needed
├── pyproject.toml               tutor.plugin.v1 entry point
└── tutornelc/
    ├── plugin.py                config, app sync, patches, init task
    ├── patches/
    │   └── openedx-dockerfile-post-python-requirements
    └── templates/nelc/
        └── openedx-nelc-features/          the Django app
            └── nelc/certification/
                ├── apps.py                 plugin_app: URLs, settings, signals
                ├── models.py               the five models
                ├── receivers.py            COURSE_ENROLLMENT_CREATED
                ├── api/                    the one endpoint
                ├── migrations/
                └── management/commands/seed_nelc_demo.py
```

The Django app is vendored inside the Tutor plugin so that this exercise is one repository.
For a real deployment I would split it into its own versioned repo, installed from a pinned
tag, the way [tutor-contrib-wikilearn](https://github.com/wikimedia/tutor-contrib-wikilearn)
installs `openedx-wikilearn-features`. The reasoning is in the note.
