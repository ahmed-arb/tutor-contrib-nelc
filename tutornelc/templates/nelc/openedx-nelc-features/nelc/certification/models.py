"""
Models for the partner certification domain.

Five tables, which is the whole of the working slice. What is deliberately NOT
here (Track, TrackStep, Vendor, CertificationStandard, TrackEnrollment,
LearnerTrackSummary, Certification) is designed in docs/erd.md and argued in
ARCHITECTURE.md. Building it was not needed to prove the approach, and the
brief asked for the minimum.

Two rules this module holds to:

1. We do not duplicate platform identity. LearnerRecord hangs off auth_user.
2. We do not hold foreign keys into platform tables. Courses are referenced by
   key string. This follows the Proposed Catalog Plugin: "It will have
   references to courses, but it will not store them directly to ensure data
   integrity and never be out of date, like discovery."
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

User = get_user_model()


class PartnerCompany(TimeStampedModel):
    """
    An implementation partner whose staff we certify.

    The scoping root. Every coach group and every learner record belongs to
    exactly one partner, and that is what makes "a coach must not see learners
    outside their group" enforceable with a predicate rather than a convention.
    """

    code = models.SlugField(
        max_length=64,
        unique=True,
        help_text=_("Stable short code, e.g. 'northwind'. Used in API responses."),
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Partner company")
        verbose_name_plural = _("Partner companies")

    def __str__(self):
        return self.name


class Tier(TimeStampedModel):
    """
    A certification tier.

    A table rather than integer choices on LearnerRecord for two reasons. The
    tier gate is a rank comparison, so rank has to be data the query can read.
    And the business will add tiers; that must not require a code deploy.

    ``rank`` is unique and ordered: higher rank means more advanced.
    """

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    rank = models.PositiveIntegerField(
        unique=True,
        help_text=_("Ordering. Higher is more advanced. Tier gating compares ranks."),
    )

    class Meta:
        ordering = ["rank"]

    def __str__(self):
        return f"{self.name} (rank {self.rank})"


class CoachGroup(TimeStampedModel):
    """
    A group of learners from one partner company, reviewed by one coach.

    The coach is a plain LMS user. We do not mint a parallel coach identity;
    being a coach is having a row here.
    """

    coach = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="nelc_coached_groups",
        help_text=_("LMS user who coaches this group."),
    )
    partner = models.ForeignKey(
        PartnerCompany,
        on_delete=models.PROTECT,
        related_name="coach_groups",
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["partner__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["coach", "partner", "name"],
                name="unique_coach_group_per_partner",
            )
        ]

    def __str__(self):
        return f"{self.name} @ {self.partner.code} (coach: {self.coach.username})"


class LearnerRecord(TimeStampedModel):
    """
    A learner's partner company and current certification tier.

    One row per learner, keyed to the LMS user. Everything the platform already
    knows about this person (name, email, enrollments, grades) stays in the
    platform and is read by joining on user_id.

    There is no employee_id column, and that is a decision rather than an
    omission. See ARCHITECTURE.md, "What I'd defer or decline".
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="nelc_learner_record",
    )
    partner = models.ForeignKey(
        PartnerCompany,
        on_delete=models.PROTECT,
        related_name="learner_records",
    )
    tier = models.ForeignKey(
        Tier,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="learner_records",
        help_text=_("Current tier. Null means not yet tiered, which gates them out of everything."),
    )
    coach_group = models.ForeignKey(
        CoachGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
        help_text=_("A learner sits under at most one coach at a time."),
    )

    class Meta:
        ordering = ["user__username"]
        indexes = [
            # The coach view reads by group. The partner column is in the index
            # because the scoping query always filters on both.
            models.Index(fields=["coach_group", "partner"], name="nelc_lr_group_partner_idx"),
        ]

    def __str__(self):
        return f"{self.user.username} ({self.partner.code})"

    def clean(self):
        """
        A learner's coach group must belong to the learner's own partner.

        Without this, a mis-set coach_group would put a learner from partner A
        into a group belonging to partner B, and the coach endpoint would
        happily return them. The API filters on partner as well as group so
        that bad data still cannot leak, but the invariant belongs here too.
        """
        super().clean()
        if self.coach_group_id and self.coach_group.partner_id != self.partner_id:
            raise ValidationError(
                {"coach_group": _("Coach group belongs to a different partner company.")}
            )

    def meets_tier(self, required_tier):
        """
        Whether this learner may join something requiring ``required_tier``.

        This is the tier gate in full. It is a rank comparison, which is the
        entire reason Tier.rank is a column. Nothing calls it yet because Track
        is not built in the slice; it is here because the note claims the gate
        is cheap and it should be possible to check that claim.
        """
        if required_tier is None:
            return True
        if self.tier is None:
            return False
        return self.tier.rank >= required_tier.rank


class LearnerActivity(models.Model):
    """
    Append-only record of things a learner did.

    Written by the enrollment receiver. This is the thinnest honest version of
    the brief's "the partner program team receives an ongoing record of learner
    activity and outcomes", and it is also the substrate the denormalised
    LearnerTrackSummary rollup would be built from.

    Append-only on purpose: no updated field, no soft delete. If a coach
    adjusts a learner's progress, that is a new row stating who did it, never an
    edit to an old one. See ARCHITECTURE.md on stakeholder request 2.
    """

    ENROLLED = "course_enrollment_created"
    STEP_COMPLETED = "step_completed"
    TIER_CHANGED = "tier_changed"
    COACH_ADJUSTMENT = "coach_adjustment"

    EVENT_TYPE_CHOICES = [
        (ENROLLED, _("Course enrollment created")),
        (STEP_COMPLETED, _("Step completed")),
        (TIER_CHANGED, _("Tier changed")),
        (COACH_ADJUSTMENT, _("Coach adjustment")),
    ]

    learner_record = models.ForeignKey(
        LearnerRecord,
        on_delete=models.CASCADE,
        related_name="activity",
    )
    event_type = models.CharField(max_length=64, choices=EVENT_TYPE_CHOICES, db_index=True)
    course_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Course key string, e.g. 'course-v1:org+course+run'. Never a foreign key."),
    )
    # Who caused this, when it was not the learner. Null means the learner did
    # it themselves. The audit column that makes a coach adjustment attributable.
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="nelc_caused_activity",
    )
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    context = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name_plural = _("Learner activity")
        indexes = [
            models.Index(fields=["learner_record", "-occurred_at"], name="nelc_activity_feed_idx"),
        ]

    def __str__(self):
        return f"{self.learner_record_id}: {self.event_type} @ {self.occurred_at:%Y-%m-%d %H:%M}"
