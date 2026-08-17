"""
Signal receivers.

One receiver: react when a learner joins a course. Connected declaratively via
PluginSignals in apps.py, so the platform owns the wiring.
"""

import logging

from openedx_events.learning.data import CourseEnrollmentData

from nelc.certification.models import LearnerActivity, LearnerRecord

log = logging.getLogger(__name__)


def on_course_enrollment_created(signal, sender, enrollment: CourseEnrollmentData, **kwargs):
    """
    Stamp a learner's activity feed when they enroll in a course.

    Fires on openedx-events COURSE_ENROLLMENT_CREATED, which edx-platform emits
    from CourseEnrollment. We take the LMS user id off the event payload rather
    than re-querying, and we no-op for anyone who is not a tracked learner:
    plenty of people enroll in courses on this platform without being a
    partner's staff member, and that is not an error.

    Deliberately cheap. This runs inside the enrollment request, so it is one
    indexed SELECT plus one INSERT. When this grows into maintaining the
    LearnerTrackSummary rollup, it moves to the event bus rather than getting
    heavier here. See ARCHITECTURE.md, "Approach".
    """
    user_id = enrollment.user.id
    course_key = str(enrollment.course.course_key)

    learner_record = (
        LearnerRecord.objects.filter(user_id=user_id).only("id").first()
    )
    if learner_record is None:
        log.debug(
            "[nelc] enrollment in %s by user %s is not a tracked learner, skipping",
            course_key,
            user_id,
        )
        return

    LearnerActivity.objects.create(
        learner_record=learner_record,
        event_type=LearnerActivity.ENROLLED,
        course_key=course_key,
        occurred_at=enrollment.creation_date,
        context={"mode": enrollment.mode, "is_active": enrollment.is_active},
    )
    log.info(
        "[nelc] recorded enrollment activity: learner_record=%s course=%s",
        learner_record.id,
        course_key,
    )
