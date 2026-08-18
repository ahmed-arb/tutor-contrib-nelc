"""Serializers for the coach group endpoint."""

from rest_framework import serializers

from nelc.certification.models import CoachGroup, LearnerRecord


class LearnerRecordSerializer(serializers.ModelSerializer):
    """A group member as their coach sees them."""

    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    tier = serializers.CharField(source="tier.code", read_only=True, default=None)
    tier_rank = serializers.IntegerField(source="tier.rank", read_only=True, default=None)

    class Meta:
        model = LearnerRecord
        fields = ["id", "username", "email", "tier", "tier_rank"]


class CoachGroupSerializer(serializers.ModelSerializer):
    """
    A coach group and its members.

    Contract: the caller must attach a ``scoped_members`` list to each group
    before serializing. This serializer never queries for members itself, and
    that is deliberate: the scoping rule is the security boundary, so it lives
    in exactly one place (``CoachOwnGroupView``) rather than being reachable
    from two. A missing attribute is an AttributeError rather than a silent
    empty list, because quietly returning nothing would hide a wiring mistake.
    """

    partner = serializers.CharField(source="partner.code", read_only=True)
    partner_name = serializers.CharField(source="partner.name", read_only=True)
    members = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = CoachGroup
        fields = ["id", "name", "partner", "partner_name", "member_count", "members"]

    def get_members(self, group):
        return LearnerRecordSerializer(group.scoped_members, many=True).data

    def get_member_count(self, group):
        return len(group.scoped_members)
