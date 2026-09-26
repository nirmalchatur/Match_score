"""
Application tracker endpoints.

Every query is scoped by ``user=request.user``. That is the whole tenant
boundary: there is no code path in this module that can read or write another
account's applications, and a guessed id resolves to 404 rather than 403 so the
API never confirms that an id exists.
"""

from django.db.models import Count, Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .dashboard import dashboard_stats
from .models import Application
from .serializers import ApplicationSerializer


#: select_related pulls the job and resume rows in the same query. The tracker
#: renders a label for every row, so without this it would be one extra query
#: per application -- the N+1 that matters most here.
_FIELDS = ("job", "tailored_resume")


class ApplicationListView(APIView):
    """GET/POST /api/applications/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):

        applications = Application.objects.filter(
            user=request.user
        ).select_related(*_FIELDS)

        status_filter = request.query_params.get("status")
        job_id = request.query_params.get("job")

        if status_filter:
            applications = applications.filter(status=status_filter.upper())

        if job_id:
            try:
                applications = applications.filter(job_id=int(job_id))
            except (TypeError, ValueError):
                # A malformed id matches nothing rather than erroring, so a
                # bad query string cannot become a 500.
                applications = applications.none()

        # `?summary=1` drives the tracker's status counters from the same
        # scoped queryset, so the counts can never disagree with the list.
        if request.query_params.get("summary"):
            return Response(self._summary(request.user))

        serializer = ApplicationSerializer(
            applications,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):

        serializer = ApplicationSerializer(
            data=request.data,
            context={"request": request},
        )

        if not serializer.is_valid():
            return Response(
                {
                    "error": "Could not create the application.",
                    "detail": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # The owner always comes from the authenticated session, never from the
        # payload. `user` is not a serializer field at all, so a client-supplied
        # user id has nothing to bind to.
        application = serializer.save(user=request.user)

        return Response(
            ApplicationSerializer(application).data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _summary(user) -> dict:
        """Status counts for this account only, in a single query."""
        rows = (
            Application.objects.filter(user=user)
            .values("status")
            .annotate(count=Count("id"))
        )

        counts = {row["status"]: row["count"] for row in rows}

        # Every known status is present, so the UI never has to handle a
        # missing key and an empty account still renders a full row of zeros.
        for value, _label in Application.STATUS_CHOICES:
            counts.setdefault(value, 0)

        return {"counts": counts, "total": sum(counts.values())}


class ApplicationDetailView(APIView):
    """GET/PATCH/DELETE /api/applications/<pk>/"""

    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        """Scoped lookup: a foreign pk is indistinguishable from a missing one."""
        return (
            Application.objects.filter(user=request.user, pk=pk)
            .select_related(*_FIELDS)
            .first()
        )

    def get(self, request, pk):

        application = self.get_object(request, pk)
        if application is None:
            return self._not_found()

        return Response(
            ApplicationSerializer(application).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):

        application = self.get_object(request, pk)
        if application is None:
            return self._not_found()

        serializer = ApplicationSerializer(
            application,
            data=request.data,
            partial=True,
            context={"request": request},
        )

        if not serializer.is_valid():
            return Response(
                {
                    "error": "Could not update the application.",
                    "detail": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        application = serializer.save()
        # Stamp applied_at on the transition into a submitted state, in the
        # model so the rule holds for every endpoint that changes a status.
        application.mark_applied()
        application.save(update_fields=["applied_at", "updated_at"])

        return Response(
            ApplicationSerializer(application).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):

        application = self.get_object(request, pk)
        if application is None:
            return self._not_found()

        application.delete()

        return Response(
            {"deleted": True},
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _not_found():
        return Response(
            {"error": "Application not found"},
            status=status.HTTP_404_NOT_FOUND,
        )


class ApplicationStatusView(APIView):
    """
    POST /api/applications/<pk>/status/   {"status": "APPLIED"}

    A narrow endpoint for the common one-field change, so the UI does not have
    to send the whole object to move a candidate forward.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):

        application = (
            Application.objects.filter(user=request.user, pk=pk)
            .select_related(*_FIELDS)
            .first()
        )
        if application is None:
            return ApplicationDetailView._not_found()

        new_status = (request.data.get("status") or "").strip().upper()

        valid = {value for value, _label in Application.STATUS_CHOICES}
        if new_status not in valid:
            return Response(
                {
                    "error": "Unknown status.",
                    "detail": {"status": ["Must be one of: %s" % ", ".join(sorted(valid))]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        application.status = new_status
        application.mark_applied()
        application.save(update_fields=["status", "applied_at", "updated_at"])

        return Response(
            ApplicationSerializer(application).data,
            status=status.HTTP_200_OK,
        )


class DashboardStatsView(APIView):
    """
    GET /api/applications/dashboard/

    Served from the applications app because that is where the pipeline metrics
    live. Kept separate from ``/api/auth/me/`` so the dashboard can be
    refreshed without re-sending the whole account payload.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            dashboard_stats(request.user),
            status=status.HTTP_200_OK,
        )
