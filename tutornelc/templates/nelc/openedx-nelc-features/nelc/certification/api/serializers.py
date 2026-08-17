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
    """A coach group and its members."""

    partner = serializers.CharField(source="partner.code", read_only=True)
    partner_name = serializers.CharField(source="partner.name", read_only=True)
    members = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = CoachGroup
        fields = ["id", "name", "partner", "partner_name", "member_count", "members"]

    def get_members(self, group):
        # Reads the prefetched, partner-filtered queryset set up by the view.
        # Doing the filtering there rather than here keeps the scoping rule in
        # one place and keeps this method off the N+1 path.
        return LearnerRecordSerializer(group.scoped_members, many=True).data

    def get_member_count(self, group):
        return len(group.scoped_members)
