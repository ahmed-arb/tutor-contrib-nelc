"""
Stand-in for the openedx-events payload types.

Only the attribute names receivers.py reads are needed. The real classes are
attrs-based and frozen; these are plain, which is enough to drive the receiver.
"""


class UserData:
    def __init__(self, id):  # noqa: A002
        self.id = id


class CourseData:
    def __init__(self, course_key):
        self.course_key = course_key


class CourseEnrollmentData:
    def __init__(self, user, course, mode, is_active, creation_date, created_by=None):
        self.user = user
        self.course = course
        self.mode = mode
        self.is_active = is_active
        self.creation_date = creation_date
        self.created_by = created_by
