# tutor-contrib-nelc

A Tutor plugin that installs a partner certification Django app into the Open edX LMS.

This is the working slice for an architecture challenge. The reasoning behind it is in
[ARCHITECTURE.md](ARCHITECTURE.md); the data model is in [docs/erd.md](docs/erd.md).
Read the note first if you want to know why the slice stops where it does.

## What it contains

- **Five models**: `PartnerCompany`, `Tier`, `CoachGroup`, `LearnerRecord`, `LearnerActivity`.
- **One authenticated endpoint**: `GET /api/nelc/v1/coach/me/group/`, which returns the
  requesting coach's own group and refuses to expose anyone else's.
- **One enrollment-reactive receiver**: on [openedx-events](https://github.com/openedx/openedx-events) `COURSE_ENROLLMENT_CREATED`,
  writes a `LearnerActivity` row for the enrolling learner.

Nothing extra is installed for the offline-grading recommendation in the note:
[`staff-graded-xblock`](https://github.com/openedx/staff-graded-xblock) is already pinned in
Verawood's `requirements/edx/base.txt` at `4.0.0`, so the image ships it and `staffgradedxblock` is
a registered `xblock.v1` entry point out of the box. A course author enables it per course by
adding `staffgradedxblock` to the Advanced Module List in Studio. Nothing in the slice uses it yet.

Not here, on purpose: any frontend, the public catalogue, the vendor integration, and the
track and certification-standard tables. Those are argued in the note.

## Before you run

| Assumption | Value |
| --- | --- |
| Open edX release | Verawood (`OPENEDX_COMMON_VERSION` resolves to `release/verawood.1`) |
| Tutor | v22.0.1 (any v22.x should work; the plugin declares `tutor>=22.0.0,<23.0.0`) |
| Python | 3.10+ on the host, which Tutor v22 requires |
| Docker | Running, with roughly 8 GB available to it |
| Other Tutor plugins | None needed. Not `mfe`, not `indigo`. The slice is backend only |

**You will need one `tutor images build openedx`, which takes 15 to 30 minutes.** There is
no way around it and I did not want to fake one: installing a Django app into the LMS means
the app has to be in the image. That is how this would ship to production, and the brief
asked to be shown the production path rather than a shortcut. Everything after the build is
fast.

The plugin does not fork or patch [`edx-platform`](https://github.com/openedx/edx-platform). The app registers itself through the
`lms.djangoapp` entry point, which edx-platform reads at startup to extend `INSTALLED_APPS`,
mount URLs, load settings and connect signal receivers. There is no settings patch for any
of that.

## Bring it up on a clean instance

These commands use a dedicated `TUTOR_ROOT` so that nothing touches an existing Tutor
environment you may already have. Run them from the directory you cloned into.

```bash
# 0. Isolate this instance. Use any path you like; keep it exported for every step.
export TUTOR_ROOT="$PWD/tutor-root"

# 1. Tutor v22 in its own virtualenv, so the plugin cannot collide with another install.
python3 -m venv .venv
source .venv/bin/activate
pip install "tutor==22.0.1"

# 2. Confirm you are driving the right Tutor at the right root before the slow step.
which tutor              # should be the tutor inside .venv
tutor --version          # should be 22.0.1
tutor config printroot   # should be the TUTOR_ROOT you exported in step 0

# 3. Install this plugin and switch it on.
pip install -e ./tutor-contrib-nelc
tutor plugins enable nelc
tutor config save

# 4. Build the image with the Django app baked in. This is the slow step.
tutor images build openedx

# 5. Start the platform. Because the app is in INSTALLED_APPS via the entry point,
#    the platform's own migrate applies our migrations; the plugin's init task then
#    seeds demo data.
tutor local launch
```

Step 2 is not ceremony. Both the activation and `TUTOR_ROOT` are shell state that dies with the
terminal, and a `tutor` already on your PATH may be a different version pointed at a different
root. Getting that wrong is quiet rather than loud: you would build one environment and launch
another. **In any new terminal, re-run the `export` and `source` lines before anything else.**

`tutor local launch` is interactive on first run and will ask for hostnames; the defaults
(`local.openedx.io`, `studio.local.openedx.io`) are fine and are what the commands below
assume.

If you ever need to re-run just this plugin's migrations and seed without a full launch:

```bash
tutor local do init --limit=nelc
```

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

Not verified, and I would rather say so than imply otherwise: Kubernetes deployment, anything
under load, and the two-second coach view, which is a claim about a `LearnerTrackSummary` table
this slice does not build. The performance argument in the note is reasoning, not a measurement.

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
