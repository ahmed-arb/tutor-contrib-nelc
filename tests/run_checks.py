#!/usr/bin/env python
"""
Standalone checks for the claims this slice makes.

Run without Docker, without edx-platform, in a couple of seconds:

    python3 -m venv .venv-tests
    ./.venv-tests/bin/pip install "django>=4.2" djangorestframework django-model-utils
    ./.venv-tests/bin/python tests/run_checks.py

What this proves: the coach endpoint's scoping, the cross-partner guard, the tier
gate, and the enrollment receiver's logic. All of it runs the real models, the
real views, the real serializers and the real AppConfig, with only the
platform-side imports stubbed (see tests/stubs/).

What this does not prove: that the receiver is actually connected to
COURSE_ENROLLMENT_CREATED, or that the app loads via the lms.djangoapp entry
point. Those are properties of edx-platform's plugin machinery, so they are only
demonstrable on a real instance. The README says how to check them there.
"""

import os
import sys
from datetime import datetime, timezone as tz

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
APP = os.path.join(REPO, "tutornelc", "templates", "nelc", "openedx-nelc-features")

# Stubs first, so the platform imports in apps.py and receivers.py resolve.
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, APP)
sys.path.insert(0, REPO)

os.environ["DJANGO_SETTINGS_MODULE"] = "tests.settings"

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.test.utils import get_runner, setup_test_environment  # noqa: E402
from django.conf import settings as dj_settings  # noqa: E402
from rest_framework.test import APIRequestFactory, force_authenticate  # noqa: E402

RESULTS = []


def check(label, condition):
    RESULTS.append((label, bool(condition)))
    print(("  PASS  " if condition else "  FAIL  ") + label)


def main():
    setup_test_environment()
    runner = get_runner(dj_settings)()
    db_config = runner.setup_databases()
    try:
        run_checks()
    finally:
        runner.teardown_databases(db_config)

    failed = [label for label, ok in RESULTS if not ok]
    print("\n%d checks, %d failures" % (len(RESULTS), len(failed)))
    return 1 if failed else 0


def run_checks():
    from nelc.certification.api.views import CoachOwnGroupView
    from nelc.certification.models import (
        CoachGroup,
        LearnerActivity,
        LearnerRecord,
        PartnerCompany,
        Tier,
    )
    from nelc.certification.receivers import on_course_enrollment_created
    from openedx_events.learning.data import CourseData, CourseEnrollmentData, UserData

    User = get_user_model()

    north = PartnerCompany.objects.create(code="northwind", name="Northwind")
    south = PartnerCompany.objects.create(code="southwind", name="Southwind")
    associate = Tier.objects.create(code="associate", name="Associate", rank=10)
    expert = Tier.objects.create(code="expert", name="Expert", rank=30)

    coach_north = User.objects.create(username="coach_north")
    coach_south = User.objects.create(username="coach_south")
    group_north = CoachGroup.objects.create(coach=coach_north, partner=north, name="North A")
    group_south = CoachGroup.objects.create(coach=coach_south, partner=south, name="South A")

    for i in range(3):
        LearnerRecord.objects.create(
            user=User.objects.create(username="north_%d" % i),
            partner=north,
            tier=associate,
            coach_group=group_north,
        )
    for i in range(2):
        LearnerRecord.objects.create(
            user=User.objects.create(username="south_%d" % i),
            partner=south,
            tier=expert,
            coach_group=group_south,
        )

    factory = APIRequestFactory()

    def get_group_as(user):
        request = factory.get("/api/nelc/v1/coach/me/group/")
        force_authenticate(request, user=user)
        return CoachOwnGroupView.as_view()(request)

    def usernames(response):
        return {m["username"] for g in response.data["groups"] for m in g["members"]}

    print("\nCoach group scoping")
    response = get_group_as(coach_north)
    north_names = usernames(response)
    check("coach sees exactly their own members", north_names == {"north_0", "north_1", "north_2"})
    check("coach sees no other partner's learners", not north_names & {"south_0", "south_1"})
    check("partner code is reported", response.data["groups"][0]["partner"] == "northwind")
    check("member_count matches members", response.data["groups"][0]["member_count"] == 3)

    response = get_group_as(coach_south)
    check("the other coach sees only theirs", usernames(response) == {"south_0", "south_1"})

    response = get_group_as(User.objects.create(username="not_a_coach"))
    check(
        "a non-coach gets 200 and an empty list, not 403",
        response.status_code == 200 and response.data["count"] == 0,
    )

    print("\nCross-partner contamination")
    # Bypass clean() the way a bulk update or a manual data fix would.
    leaked = LearnerRecord.objects.create(
        user=User.objects.create(username="leaked"), partner=south, tier=expert
    )
    LearnerRecord.objects.filter(pk=leaked.pk).update(coach_group=group_north)

    response = get_group_as(coach_north)
    after = usernames(response)
    check("mis-assigned learner is withheld from the response", "leaked" not in after)
    check("legitimate members are unaffected", after == {"north_0", "north_1", "north_2"})

    invalid = LearnerRecord(
        user=User.objects.create(username="rejected"), partner=south, coach_group=group_north
    )
    try:
        invalid.full_clean()
        check("clean() rejects a cross-partner coach group", False)
    except ValidationError as exc:
        check("clean() rejects a cross-partner coach group", "coach_group" in exc.message_dict)

    print("\nTier gate")
    learner = LearnerRecord.objects.get(user__username="north_0")  # associate, rank 10
    check("a lower tier cannot join a higher-tier track", learner.meets_tier(expert) is False)
    check("an equal tier can join", learner.meets_tier(associate) is True)
    check("no required tier means no gate", learner.meets_tier(None) is True)
    untiered = LearnerRecord.objects.create(
        user=User.objects.create(username="untiered"), partner=north
    )
    check("an untiered learner is gated out", untiered.meets_tier(associate) is False)

    print("\nEnrollment receiver")
    tracked = LearnerRecord.objects.get(user__username="north_1")
    enrolled_at = datetime(2026, 8, 17, 12, 0, tzinfo=tz.utc)
    event = CourseEnrollmentData(
        user=UserData(id=tracked.user_id),
        course=CourseData(course_key="course-v1:OpenedX+DemoX+DemoCourse"),
        mode="audit",
        is_active=True,
        creation_date=enrolled_at,
    )
    on_course_enrollment_created(signal=None, sender=None, enrollment=event)

    activity = LearnerActivity.objects.filter(learner_record=tracked)
    check("the receiver wrote exactly one activity row", activity.count() == 1)
    row = activity.first()
    check("event type is the enrollment type", row.event_type == LearnerActivity.ENROLLED)
    check("course key is stored as a string", row.course_key == "course-v1:OpenedX+DemoX+DemoCourse")
    check("occurred_at comes from the event, not now()", row.occurred_at == enrolled_at)
    check("mode is captured in context", row.context.get("mode") == "audit")

    # An untracked user enrolling is the common case on any real platform.
    before = LearnerActivity.objects.count()
    stranger = User.objects.create(username="stranger")
    on_course_enrollment_created(
        signal=None,
        sender=None,
        enrollment=CourseEnrollmentData(
            user=UserData(id=stranger.id),
            course=CourseData(course_key="course-v1:OpenedX+DemoX+DemoCourse"),
            mode="audit",
            is_active=True,
            creation_date=enrolled_at,
        ),
    )
    check(
        "a non-learner enrolling is a no-op, not an error",
        LearnerActivity.objects.count() == before,
    )


if __name__ == "__main__":
    sys.exit(main())
