"""
Seed enough data to exercise the slice on a clean instance.

Creates two partner companies so that group isolation is actually observable:
if the scoping were wrong, coach_north would see Southwind's learners. A single
partner would not prove anything.

Idempotent. Safe to re-run, and it runs on every `tutor local do init`.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from nelc.certification.models import CoachGroup, LearnerRecord, PartnerCompany, Tier

User = get_user_model()

TIERS = [
    ("associate", "Associate", 10),
    ("professional", "Professional", 20),
    ("expert", "Expert", 30),
]

PARTNERS = [
    ("northwind", "Northwind Integrations"),
    ("southwind", "Southwind Consulting"),
]

# (username, partner_code, tier_code)
LEARNERS = [
    ("learner_north_1", "northwind", "associate"),
    ("learner_north_2", "northwind", "professional"),
    ("learner_north_3", "northwind", None),
    ("learner_south_1", "southwind", "expert"),
    ("learner_south_2", "southwind", "associate"),
]

# (coach_username, partner_code, group_name)
COACHES = [
    ("coach_north", "northwind", "Northwind Cohort A"),
    ("coach_south", "southwind", "Southwind Cohort A"),
]

PASSWORD = "nelc-demo-password"


class Command(BaseCommand):
    help = "Seed demo partners, tiers, coaches, groups and learner records."

    @transaction.atomic
    def handle(self, *args, **options):
        tiers = {}
        for code, name, rank in TIERS:
            tier, _ = Tier.objects.update_or_create(
                code=code, defaults={"name": name, "rank": rank}
            )
            tiers[code] = tier

        partners = {}
        for code, name in PARTNERS:
            partner, _ = PartnerCompany.objects.update_or_create(
                code=code, defaults={"name": name}
            )
            partners[code] = partner

        groups = {}
        for username, partner_code, group_name in COACHES:
            coach = self._user(username)
            group, _ = CoachGroup.objects.update_or_create(
                coach=coach,
                partner=partners[partner_code],
                name=group_name,
                defaults={"is_active": True},
            )
            groups[partner_code] = group

        for username, partner_code, tier_code in LEARNERS:
            user = self._user(username)
            LearnerRecord.objects.update_or_create(
                user=user,
                defaults={
                    "partner": partners[partner_code],
                    "tier": tiers[tier_code] if tier_code else None,
                    "coach_group": groups[partner_code],
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded {} tiers, {} partners, {} coach groups, {} learners. "
                "Demo password for all seeded users: {}".format(
                    len(TIERS), len(PARTNERS), len(COACHES), len(LEARNERS), PASSWORD
                )
            )
        )

    def _user(self, username):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@example.com", "is_active": True},
        )
        if created:
            user.set_password(PASSWORD)
            user.save(update_fields=["password"])
        return user
