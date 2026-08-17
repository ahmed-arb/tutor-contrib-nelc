"""
Django admin.

Present so the slice is operable without a frontend: a reviewer can create a
partner, a tier, a coach group and a learner record by hand and watch the
endpoint change. Not a substitute for the real admin surfaces, which the note
places in Studio alongside track authoring.
"""

from django.contrib import admin

from nelc.certification.models import (
    CoachGroup,
    LearnerActivity,
    LearnerRecord,
    PartnerCompany,
    Tier,
)


@admin.register(PartnerCompany)
class PartnerCompanyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")


@admin.register(Tier)
class TierAdmin(admin.ModelAdmin):
    list_display = ("rank", "code", "name")
    ordering = ("rank",)


@admin.register(CoachGroup)
class CoachGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "partner", "coach", "is_active")
    list_filter = ("partner", "is_active")
    search_fields = ("name", "coach__username")
    raw_id_fields = ("coach",)


@admin.register(LearnerRecord)
class LearnerRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "partner", "tier", "coach_group")
    list_filter = ("partner", "tier")
    search_fields = ("user__username", "user__email")
    raw_id_fields = ("user",)


@admin.register(LearnerActivity)
class LearnerActivityAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "learner_record", "event_type", "course_key", "actor")
    list_filter = ("event_type",)
    search_fields = ("learner_record__user__username", "course_key")
    raw_id_fields = ("learner_record", "actor")
    # Append-only in the admin too, so a stray click cannot rewrite history.
    readonly_fields = tuple(
        field.name for field in LearnerActivity._meta.fields if field.name != "id"
    )

    def has_delete_permission(self, request, obj=None):
        return False
