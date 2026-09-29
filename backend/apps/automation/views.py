"""
Notification endpoints.

The whole module is scoped to ``request.user`` on every query. There is no
"list all notifications" path and no way to address a row by an id from another
account: a detail lookup that forgets the user filter would expose the fact
that someone else applied to a company, so the filter is written into the
query rather than applied afterwards.
"""

from django.db.models import Count, Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, NotificationPreference

#: Cap on one page. The bell opens a list, not an archive, and an unbounded
#: response would grow forever for a long-lived account.
PAGE_SIZE = 30


def _serialize(notification: Notification) -> dict:
    """The wire shape. Never includes ``user`` -- a client has no use for it
    and it is one less identifier echoed back to a browser."""
    return {
        "id": notification.id,
        "kind": notification.kind,
        "title": notification.title,
        "body": notification.body,
        "link": notification.link,
        "is_read": notification.is_read,
        "created_at": notification.created_at,
        "read_at": notification.read_at,
    }


class NotificationListView(APIView):
    """
    GET /api/notifications/ -- this account's notifications, newest first.

    ``?unread=true`` filters to unread only, which is what the badge's
    popover uses so opening it does not require scrolling past a long read
    history.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Notification.objects.filter(user=request.user)

        if request.query_params.get("unread") in ("1", "true", "True"):
            queryset = queryset.filter(is_read=False)

        rows = list(queryset[:PAGE_SIZE])

        # One extra query for the count rather than len(rows): the badge needs
        # the total unread, which is not bounded by PAGE_SIZE.
        unread = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()

        return Response(
            {
                "results": [_serialize(row) for row in rows],
                "unread_count": unread,
            },
            status=status.HTTP_200_OK,
        )


class NotificationReadView(APIView):
    """
    POST /api/notifications/<id>/read/ -- mark one read.

    The lookup is ``filter(user=request.user, pk=...)`` rather than
    ``get(pk=...)`` followed by a check, so another account's row is a 404
    instead of a 403. A 403 would confirm the id exists, which is a small
    information leak across tenant boundaries for no benefit.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = Notification.objects.filter(
            user=request.user,
            pk=pk,
        ).first()

        if notification is None:
            return Response(
                {"error": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.mark_read()
        return Response(_serialize(notification), status=status.HTTP_200_OK)


class NotificationReadAllView(APIView):
    """
    POST /api/notifications/read-all/ -- mark everything read.

    A single UPDATE rather than a loop: on an account with hundreds of unread
    rows the per-row version is hundreds of queries, and this is called from
    the "mark all read" button in the popover.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.utils import timezone

        updated = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

        return Response({"updated": updated}, status=status.HTTP_200_OK)


class NotificationPreferenceView(APIView):
    """
    GET/PATCH /api/notifications/preferences/ -- which notifications to create.

    A GET does not report the stored row but the *effective* settings, so the
    UI shows what is actually in force (defaults on) rather than an empty
    object that looks like everything is off.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs = NotificationPreference.for_user(request.user)
        return Response(
            {
                "job_updates": prefs.job_updates,
                "job_matches": prefs.job_matches,
                "application_updates": prefs.application_updates,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        prefs = NotificationPreference.for_user(request.user)

        # Explicit allowlist. A PATCH that iterated the request body could be
        # made to write an unrelated field, and the serializer-free style used
        # here means validation has to be written down.
        for field in ("job_updates", "job_matches", "application_updates"):
            if field in request.data:
                setattr(prefs, field, bool(request.data[field]))

        prefs.save(
            update_fields=[
                "job_updates",
                "job_matches",
                "application_updates",
                "updated_at",
            ]
        )

        return Response(
            {
                "job_updates": prefs.job_updates,
                "job_matches": prefs.job_matches,
                "application_updates": prefs.application_updates,
            },
            status=status.HTTP_200_OK,
        )
