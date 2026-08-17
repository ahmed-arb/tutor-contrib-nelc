"""
The one authenticated endpoint in the slice.

GET /api/nelc/v1/coach/me/group/

Returns the requesting coach's own groups and their members. The isolation
requirement ("a coach must not see learners outside their group") is met
structurally rather than by a check that could be forgotten:

1. The URL takes no group identifier. There is no parameter through which a
   caller can name a group, so there is nothing to authorise and nothing to
   get wrong. This is why the endpoint is /coach/me/group/ and not
   /coach/groups/<id>/. An IDOR needs an object reference to tamper with, and
   this endpoint does not accept one.
2. The group queryset is filtered on coach=request.user.
3. Each member is checked against its own group's partner before being
   returned, so a learner mis-assigned across partners cannot leak even if the
   model-level invariant was bypassed by a bulk write or a data fix.

Two queries regardless of group count.
"""

import logging
from collections import defaultdict

from openedx.core.lib.api.authentication import BearerAuthenticationAllowInactiveUser
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nelc.certification.api.serializers import CoachGroupSerializer
from nelc.certification.models import CoachGroup, LearnerRecord

log = logging.getLogger(__name__)

try:  # pragma: no cover
    from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication

    _AUTH_CLASSES = (
        JwtAuthentication,
        BearerAuthenticationAllowInactiveUser,
        SessionAuthentication,
    )
except ImportError:  # pragma: no cover
    _AUTH_CLASSES = (BearerAuthenticationAllowInactiveUser, SessionAuthentication)


class CoachOwnGroupView(APIView):
    """The coach's own group roster."""

    authentication_classes = _AUTH_CLASSES
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        groups = list(
            CoachGroup.objects.filter(coach=request.user, is_active=True).select_related("partner")
        )
        if not groups:
            # Authenticated but coaches nobody. 200 with an empty list rather
            # than 403: whether you coach anyone is not a permission question,
            # and a 403 would distinguish "not a coach" from "no groups".
            log.debug("[nelc] user %s requested coach group, coaches nothing", request.user.id)
            return Response({"count": 0, "groups": []})

        groups_by_id = {group.id: group for group in groups}

        members = LearnerRecord.objects.select_related("user", "tier").filter(
            coach_group_id__in=groups_by_id.keys()
        )

        members_by_group = defaultdict(list)
        for member in members:
            group = groups_by_id[member.coach_group_id]
            if member.partner_id != group.partner_id:
                # Defence in depth. LearnerRecord.clean() forbids this, but
                # clean() does not run on bulk writes or manual SQL, and the
                # failure mode here is handing a coach another company's roster.
                log.warning(
                    "[nelc] cross-partner learner %s in group %s, withholding",
                    member.id,
                    group.id,
                )
                continue
            members_by_group[group.id].append(member)

        for group in groups:
            group.scoped_members = members_by_group.get(group.id, [])

        return Response(
            {
                "count": len(groups),
                "groups": CoachGroupSerializer(groups, many=True).data,
            }
        )
