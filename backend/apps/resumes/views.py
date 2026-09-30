"""
Resume endpoints.

Every query is scoped to the authenticated account. Uploads are validated
(type, extension, size) and parsed through the existing ResumeParser so the
master resume is a real, profiled document rather than a stored blob.

This module is a thin HTTP layer. The tailoring decisions -- which resume and
job are involved, which provider and key apply, what is recorded, what is
persisted -- live in :mod:`apps.resumes.services.tailoring_service`, so they can
be tested without a request and reused from a worker later.
"""

import logging
import os

from django.conf import settings
from django.http import FileResponse, HttpResponse
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import qualities
from .models import Resume, ResumeProfile
from .serializers import ResumeSerializer
from .services import tailoring_service
from .services.tailoring_service import TailoringError

from apps.ai import factory, progress, selection
from apps.ai.exceptions import AITailoringValidationError, AIError
from apps.common.models import ActivityEvent
from apps.users.models import ProviderCredential

from apps.resumes.services.document_service import render_resume_document

from apps.resumes.services.parser import ResumeParser
from apps.resumes.services.resume_profile import ResumeProfile as ResumeProfileService
from apps.common.throttling import (
    AIHourlyRateThrottle,
    AIUserRateThrottle,
    DocumentRateThrottle,
    ProgressRateThrottle,
)

logger = logging.getLogger(__name__)


class InvalidResumeUpload(ValueError):
    """Raised when an uploaded file fails validation."""


def validate_resume_upload(uploaded):
    """Validate a candidate master-resume upload.

    Raises InvalidResumeUpload with a user-facing message.
    """
    if uploaded is None:
        raise InvalidResumeUpload("No file was provided.")

    name = getattr(uploaded, "name", "") or ""

    extension = os.path.splitext(name)[1].lower()
    if extension not in settings.ALLOWED_RESUME_EXTENSIONS:
        raise InvalidResumeUpload(
            f"Only PDF resumes are supported. Received '{extension or 'unknown'}'."
        )

    content_type = (getattr(uploaded, "content_type", "") or "").lower()
    if content_type and content_type not in settings.ALLOWED_RESUME_CONTENT_TYPES:
        raise InvalidResumeUpload(
            f"Unsupported file type '{content_type}'. Please upload a PDF."
        )

    size = getattr(uploaded, "size", None)
    if size is not None and size > settings.MAX_RESUME_UPLOAD_BYTES:
        limit_mb = settings.MAX_RESUME_UPLOAD_BYTES // (1024 * 1024)
        raise InvalidResumeUpload(
            f"Resume is too large. Maximum size is {limit_mb} MB."
        )

    return True


class ResumeListView(APIView):

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):

        # Tenant boundary: only ever this account's resumes.
        resumes = Resume.objects.filter(
            user=request.user
        ).order_by(
            "-created_at"
        )

        serializer = ResumeSerializer(
            resumes,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):

        serializer = ResumeSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        resume = None

        try:
            # 0. Validate the upload before touching the database
            validate_resume_upload(
                request.FILES.get("file")
            )

            # 1. Save uploaded resume, owned by the current account
            resume = serializer.save(
                user=request.user
            )

            # 2. Extract text from PDF
            resume_text = ResumeParser.extract_text(
                resume.file.path
            )

            if not resume_text:
                raise ValueError(
                    "Could not extract text from resume. "
                    "The PDF may be a scanned image."
                )

            # 3. Build structured profile
            profile_data = ResumeProfileService.build(
                resume_text
            )

            # 4. Create ResumeProfile database record
            ResumeProfile.objects.update_or_create(
                resume=resume,
                defaults={
                    "skills": profile_data.get(
                        "skills",
                        []
                    ),
                    "experience": profile_data.get(
                        "experience",
                        {}
                    ),
                    "education": profile_data.get(
                        "education",
                        ""
                    ),
                    "projects": profile_data.get(
                        "projects",
                        ""
                    ),
                    "certifications": profile_data.get(
                        "certifications",
                        ""
                    ),
                },
            )

            # 5. Record it, then return the resume. The activity row is written
            #    before the response because it describes an upload that has
            #    already succeeded; record() cannot raise, so a failed insert
            #    costs a history row and not the user's upload.
            ActivityEvent.record(
                request.user,
                ActivityEvent.RESUME_UPLOADED,
                object_type="resume",
                object_id=resume.id,
                summary=resume.name,
                metadata={
                    "resume_type": resume.resume_type,
                    "skills": len(profile_data.get("skills") or []),
                },
            )

            return Response(
                ResumeSerializer(resume).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:

            # Delete uploaded resume if
            # profile generation fails
            if resume is not None:
                resume.delete()

            return Response(
                {
                    "error": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class ResumeDetailView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        try:
            # Scoped lookup prevents IDOR across accounts.
            resume = Resume.objects.get(
                pk=pk,
                user=request.user,
            )

        except Resume.DoesNotExist:

            return Response(
                {
                    "error": "Resume not found"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ResumeSerializer(
            resume
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        """Remove one of the account's own resumes."""

        try:
            resume = Resume.objects.get(
                pk=pk,
                user=request.user,
            )
        except Resume.DoesNotExist:
            return Response(
                {"error": "Resume not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        was_master = resume.is_master
        resume.delete()

        return Response(
            {
                "deleted": True,
                "had_master": was_master,
            },
            status=status.HTTP_200_OK,
        )


class MasterResumeView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        try:

            resume = Resume.objects.get(
                user=request.user,
                is_master=True,
            )

        except Resume.DoesNotExist:

            return Response(
                {
                    "error": "Master resume not found"
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except Resume.MultipleObjectsReturned:

            return Response(
                {
                    "error": "Multiple master resumes found"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ResumeSerializer(
            resume
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class SetMasterResumeView(APIView):
    """
    POST /api/resumes/<pk>/set-master/

    Promotes one of the account's own resumes to master. Any previous master
    is demoted so the account always has at most one, which the job pipeline
    depends on.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):

        try:
            resume = Resume.objects.get(
                pk=pk,
                user=request.user,
            )
        except Resume.DoesNotExist:
            return Response(
                {"error": "Resume not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        Resume.objects.filter(
            user=request.user,
            is_master=True,
        ).exclude(
            pk=resume.pk,
        ).update(
            is_master=False
        )

        resume.is_master = True
        resume.resume_type = "MASTER"
        resume.save(
            update_fields=["is_master", "resume_type"]
        )

        # Recorded because "which resume is the master" changes every score the
        # user sees from here on, and a support question about a sudden drop is
        # usually this row.
        ActivityEvent.record(
            request.user,
            ActivityEvent.MASTER_RESUME_CHANGED,
            object_type="resume",
            object_id=resume.id,
            summary=resume.name,
        )

        return Response(
            ResumeSerializer(resume).data,
            status=status.HTTP_200_OK,
        )



# ---------------------------------------------------------------------------
# AI tailoring
# ---------------------------------------------------------------------------


def _ai_error_response(exc: AIError):
    """
    Map an AI-layer error onto an HTTP response.

    Only ``exc.message`` is returned. ``exc.detail`` carries provider internals
    (base URL, model name, raw response bodies) and stays in the logs, so the
    client learns what went wrong without learning how the backend is wired.
    """
    return Response(
        {
            "error": exc.message,
            "code": exc.code,
        },
        status=exc.status_code,
    )


def _get_master_resume(user):
    return Resume.objects.filter(user=user, is_master=True).first()


def _master_profile(user) -> ResumeProfile | None:
    """
    The signed-in account's master ``ResumeProfile``, or ``None``.

    Created on demand: an account can have a master resume whose profile row
    was never written (a profile-less upload predates the profile services),
    and the qualities endpoint should still work for it rather than 404.
    """
    master = (
        Resume.objects.filter(user=user, is_master=True)
        .order_by("-created_at")
        .first()
    )
    if master is None:
        return None

    profile, _ = ResumeProfile.objects.get_or_create(resume=master)
    return profile


class QualitiesView(APIView):
    """
    GET/PUT ``/api/resumes/qualities/`` -- the candidate's chosen qualities.

    Split from ``/api/resumes/master/`` because the two answer different
    questions. That endpoint reports what the *parser* found; this one holds
    what the *user* claims, and it has a validation rule the other does not:
    at least :data:`~apps.resumes.qualities.MINIMUM_TOTAL` across all three
    categories, and at least one in each.

    ``GET`` also returns the catalogue and the minimum, so the picker does not
    hard-code options that the server would then reject. A client that sends
    fewer than the minimum is refused -- the UI disables its save button, but
    that is a courtesy, not the control.
    """

    permission_classes = [IsAuthenticated]

    def _payload(self, profile) -> dict:
        selected = qualities.normalize(profile.qualities)
        return {
            "qualities": selected,
            "selected_count": qualities.count(selected),
            "catalogue": qualities.CATALOGUE,
            "labels": qualities.KIND_LABELS,
            "minimum_total": qualities.MINIMUM_TOTAL,
            "kinds": list(qualities.KINDS),
            # Groups with nothing chosen. A hint the picker can show, not an
            # error: see qualities.uncovered_groups for why it is not enforced.
            "uncovered_groups": qualities.uncovered_groups(selected),
        }

    def get(self, request):
        profile = _master_profile(request.user)
        if profile is None:
            return Response(
                {
                    "error": "Upload a master resume before choosing qualities.",
                    "qualities": qualities.normalize(None),
                    "selected_count": 0,
                    "catalogue": qualities.CATALOGUE,
                    "labels": qualities.KIND_LABELS,
                    "minimum_total": qualities.MINIMUM_TOTAL,
                    "kinds": list(qualities.KINDS),
                    "uncovered_groups": list(qualities.KINDS),
                },
                status=status.HTTP_200_OK,
            )

        return Response(self._payload(profile), status=status.HTTP_200_OK)

    def put(self, request):
        profile = _master_profile(request.user)
        if profile is None:
            return Response(
                {"error": "Upload a master resume before choosing qualities."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw = request.data.get("qualities", request.data)
        try:
            selected = qualities.validate_selection(raw)
        except qualities.QualityError as exc:
            # 400 with a human-readable message. The UI shows it as-is, which
            # is why it is worded as an instruction rather than as a code.
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile.qualities = selected
        profile.save(update_fields=["qualities", "updated_at"])

        return Response(self._payload(profile), status=status.HTTP_200_OK)


def _tailoring_error_response(exc: TailoringError) -> Response:
    """
    Map a service-level refusal onto HTTP.

    The service decides *what* went wrong; the status code it suggests is
    honoured here rather than recomputed, so one place owns the mapping. Only
    ``as_dict()`` is read, which carries no internals.
    """
    return Response(exc.as_dict(), status=exc.status_code)


class TailorResumeView(APIView):
    throttle_classes = [AIUserRateThrottle, AIHourlyRateThrottle]
    """
    POST /api/resumes/tailor/  {"job_id": 12}

    Produces a tailoring of the caller's master resume for one of the caller's
    jobs, and returns it as a **before/after review payload**. Nothing is saved:
    the user reviews first, and saving is a separate explicit call.

    The request carries only an id. Resume content, the job description and the
    match analysis are all loaded server-side from this account's own rows, so a
    client can never ask the AI to tailor content it does not own.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            payload = tailoring_service.generate_tailoring(
                request.user, request.data.get("job_id")
            )
        except AITailoringValidationError as exc:
            # Fabricated output is never returned as a suggestion. The
            # violations come back so the UI can explain the rejection.
            return Response(
                {
                    "error": exc.message,
                    "code": exc.code,
                    "violations": exc.violations,
                },
                status=exc.status_code,
            )
        except AIError as exc:
            return _ai_error_response(exc)
        except TailoringError as exc:
            return _tailoring_error_response(exc)

        return Response(payload, status=status.HTTP_200_OK)


class SaveTailoredResumeView(APIView):
    """
    POST /api/resumes/tailor/save/  {"job_id": 12, "result": {...}}

    Saves a reviewed tailoring as a **new** Resume row. The master is never
    modified: this creates a separate TAILORED resume that points back at the
    master and the job it was written for.

    The submitted result is re-validated against the current master resume before
    anything is written, so content edited in the browser cannot be smuggled past
    the factual checks that the tailor endpoint applied.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            tailored, _validation = tailoring_service.save_tailored_resume(
                request.user,
                request.data.get("job_id"),
                request.data.get("result"),
                provider_name=request.data.get("provider") or "",
            )
        except TailoringError as exc:
            return _tailoring_error_response(exc)

        return Response(
            ResumeSerializer(tailored).data,
            status=status.HTTP_201_CREATED,
        )


class AIProviderStatusView(APIView):
    """
    GET /api/resumes/tailor/status/

    Lets the UI hide or disable the tailor button when no provider is configured,
    without the user having to trigger a failed request to find out.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # The effective provider is per user, not global: the deployment picks a
        # default, but this account may have chosen otherwise. The reason is
        # returned alongside it, because "why is my resume going to a hosted
        # provider" is a question the user is entitled to have answered here
        # rather than by reading logs.
        effective, reason = selection.resolve_provider_name(request.user)
        described = factory.describe_provider(effective)
        described["selection_reason"] = reason
        described["deployment_default"] = selection.default_provider_name()

        # Availability is per user, not global. A hosted provider is unusable
        # until a key exists -- but "a key exists" now means the user's own
        # credential *or* the deployment's env fallback, so a deploy that sets
        # GEMINI_API_KEY correctly reports itself ready instead of disabling
        # tailoring for everyone who never pasted a key.
        described["requires_user_key"] = selection.provider_needs_user_key(effective)
        described["user_key_configured"] = ProviderCredential.objects.filter(
            user=request.user,
            provider=effective,
        ).exists()
        # Reported separately so the UI can say "using the app's key" rather
        # than silently changing whose quota is being spent. Never the value.
        described["deployment_key_configured"] = selection.has_deployment_key(
            effective
        )

        return Response(described, status=status.HTTP_200_OK)


class TailorProgressView(APIView):
    """
    GET /api/resumes/tailor/progress/?since=<elapsed>

    Live progress for this account's most recent tailoring run.

    Polling rather than SSE on purpose. The alternative holds a request open
    for the length of a run, and a run on CPU is measured in minutes: that
    pins a worker, and gunicorn has a fixed number of them, so a handful of
    concurrent users would exhaust the pool. A poll is a few hundred bytes and
    costs nothing held open.

    ``since`` is the ``elapsed`` of the last event the client saw, so a
    repeated poll returns only what is new. The server answers with its own
    ``elapsed`` for the next call to use as the cursor.
    """

    permission_classes = [IsAuthenticated]
    # Replaces the default user scope rather than stacking on it: a long run
    # would otherwise spend the user's whole API budget on status calls.
    throttle_classes = [ProgressRateThrottle]

    def get(self, request):
        raw = request.query_params.get("since")
        try:
            since = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            # A malformed cursor is the client's problem, not a reason to
            # return a 500: re-sending the whole buffer is a correct answer.
            since = None

        return Response(progress.snapshot(request.user.pk, since), status=status.HTTP_200_OK)


class ResumeDownloadView(APIView):
    throttle_classes = [DocumentRateThrottle]
    """
    GET /api/resumes/<pk>/download/<fmt>/   fmt is "docx" or "pdf"

    Renders the resume on demand and returns it as a file attachment.

    Security
    --------
    The lookup is ``Resume.objects.filter(user=request.user, pk=pk)``, so the
    tenant boundary is enforced by the query itself. A resume owned by someone
    else is indistinguishable from one that does not exist -- both 404. The
    client never supplies a user id, and the response body is the document
    itself, so no filesystem path is ever disclosed.
    """

    permission_classes = [IsAuthenticated]
    #: The master is downloadable like any other resume: the user owns it, and
    #: rendering it is a read-only operation that cannot alter it.
    allowed_formats = ("docx", "pdf")

    def get(self, request, pk, fmt):

        fmt = (fmt or "").lower()
        if fmt not in self.allowed_formats:
            return Response(
                {
                    "error": "Unsupported format. Use docx or pdf.",
                    "code": "unsupported_format",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        resume = Resume.objects.filter(user=request.user, pk=pk).first()
        if resume is None:
            return Response(
                {"error": "Resume not found.", "code": "resume_missing"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            payload, content_type, filename = render_resume_document(
                resume, request.user, fmt
            )
        except ValueError as exc:
            logger.warning("resume.render_failed resume=%s fmt=%s", pk, fmt)
            return Response(
                {
                    "error": str(exc) if str(exc) else "This resume has no content to render.",
                    "code": "render_failed",
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        response = HttpResponse(payload, content_type=content_type)
        # A quoted, ASCII-safe filename; the service derives it from the
        # resume's own name rather than from anything the client sent.
        response["Content-Disposition"] = 'attachment; filename="%s"' % filename
        response["Content-Length"] = str(len(payload))
        # Personal documents must not be cached by shared proxies.
        response["Cache-Control"] = "private, no-store"
        return response


class ResumeFileView(APIView):
    """
    GET /api/resumes/<pk>/file/ -- the originally uploaded document.

    Why this exists rather than linking MEDIA_URL directly
    ------------------------------------------------------
    The "Open" button used to point at the raw upload path, which was broken
    twice over:

    1. ``api.fileUrl`` returned a root-relative ``/media/...`` unchanged, so
       the browser resolved it against the *frontend* origin. The SPA is on
       Vercel and the API on Render, so the request went to the wrong host and
       404'd.
    2. Even with the right host, nothing serves ``/media/`` in production.
       ``django.conf.urls.static.static()`` is a no-op unless ``DEBUG`` is on
       -- verified: it returns zero routes here -- so the route in
       ``config/urls.py`` only ever worked in development.

    Routing through an authenticated view fixes both, and it is also the only
    version that is *safe*. Serving uploads as plain static files would make
    every resume world-readable at a guessable URL, bypassing the tenant
    boundary every other endpoint in this project enforces by scoping the
    query to ``request.user``. A resume is a personal document; it is not a
    public asset.

    The download endpoint renders a fresh document from the structured profile
    and is unaffected -- it never went through MEDIA_URL.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        # Scoped by owner, so another account's id is indistinguishable from a
        # missing one -- both 404, never 403, which would confirm it exists.
        resume = Resume.objects.filter(user=request.user, pk=pk).first()
        if resume is None or not resume.file:
            return Response(
                {"error": "Resume not found.", "code": "resume_missing"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            # `open` on the FieldFile, not read(): read() loads the whole
            # document into memory, and a 10 MB PDF per request is a way to
            # make the worker hold a lot of nothing.
            handle = resume.file.open("rb")
        except (FileNotFoundError, OSError):
            # The row points at a file that is gone -- a deploy that lost the
            # media volume, most likely. Say so plainly rather than 500.
            logger.warning("resume.file_missing resume=%s", pk)
            return Response(
                {
                    "error": "The uploaded file is no longer available. Please re-upload it.",
                    "code": "file_missing",
                },
                status=status.HTTP_410_GONE,
            )

        # `inline`, not `attachment`: this is what "Open" means, and the
        # browser should render the PDF in a tab rather than download it.
        response = FileResponse(handle, content_type="application/pdf")
        name = os.path.basename(resume.file.name) or "resume.pdf"
        response["Content-Disposition"] = 'inline; filename="%s"' % name
        # Personal document: never cached by a shared proxy or the browser's
        # shared cache.
        response["Cache-Control"] = "private, no-store"
        return response
