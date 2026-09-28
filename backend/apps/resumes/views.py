"""
Resume endpoints.

Every query is scoped to the authenticated account. Uploads are validated
(type, extension, size) and parsed through the existing ResumeParser so the
master resume is a real, profiled document rather than a stored blob.
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

from apps.ai import factory
from apps.ai.exceptions import (
    AIConfigurationError,
    AIError,
    AITailoringValidationError,
)
from apps.ai.schemas import normalise
from apps.ai.tailor import ResumeTailor, build_source_resume
from apps.ai.validators import validate as validate_tailoring
from apps.jobs.models import Job
from apps.jobs.services.jd_profile import JDProfile
from apps.users.crypto import CredentialCryptoError
from apps.users.models import ProviderCredential

from apps.resumes.services.document_service import render_resume_document

from apps.resumes.services.parser import ResumeParser
from apps.resumes.services.resume_profile import ResumeProfile as ResumeProfileService

logger = logging.getLogger(__name__)


def _user_api_key(user) -> str:
    """Decrypt the caller's own provider key, or return "" if they have none.

    Returns a plain string rather than the model so that a caller cannot
    accidentally keep a database object (and therefore the ciphertext) alive
    past the request, and so the "no key" case needs no branching at the call
    site.

    Raises :class:`CredentialCryptoError` only when a row exists but cannot be
    decrypted; ``reveal_key`` removes that row on the way out, so the next
    request honestly reports "not configured".
    """
    credential = ProviderCredential.objects.filter(
        user=user,
        provider="gemini",
    ).first()

    if credential is None:
        return ""

    return credential.reveal_key()


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

            # 5. Return resume
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


def _stored_profile(resume) -> dict:
    """The stored profile dict, in the shape ``build_source_resume`` expects."""
    try:
        profile = resume.profile
    except ResumeProfile.DoesNotExist:
        return {}

    return {
        "summary": "",
        "skills": profile.skills or [],
        "experience": profile.experience or {},
        "education": profile.education or "",
        "projects": profile.projects or "",
        "certifications": profile.certifications or "",
        # Chosen qualities ride along with the parsed profile so the tailoring
        # prompt and the match analysis can both see them. Normalised on read
        # as well as on write, because a row written before this field existed
        # holds {} rather than the canonical three-key shape.
        "qualities": qualities.normalize(profile.qualities),
    }


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


def _load_job(user, job_id):
    """
    Fetch a job **scoped to the requesting account**.

    Scoping by ``user`` in the query itself is what stops User A from tailoring
    against User B's job: there is no id-guessing path here at all.
    """
    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        return None

    return Job.objects.filter(user=user, id=job_id).first()


def _tailoring_context(user, job_id):
    """
    Gather everything the tailoring needs, or return an error Response.

    Returns ``(master_resume, job, jd_profile, error_response)``.
    """
    master = _get_master_resume(user)
    if master is None:
        return None, None, None, Response(
            {
                "error": "No master resume found. Upload one before tailoring.",
                "code": "resume_missing",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    job = _load_job(user, job_id)
    if job is None:
        return None, None, None, Response(
            {"error": "Job not found.", "code": "job_missing"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not (job.description or "").strip():
        return None, None, None, Response(
            {
                "error": "This job has no stored description to tailor against.",
                "code": "job_description_missing",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Reuse the existing JD analysis rather than re-deriving it, so the tailoring
    # emphasis agrees with the match score already shown to the user.
    try:
        jd_profile = JDProfile.build(job.description)
    except ValueError:
        return None, None, None, Response(
            {
                "error": "This job has no usable description to tailor against.",
                "code": "job_description_missing",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return master, job, jd_profile, None


class TailorResumeView(APIView):
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

        master, job, jd_profile, error = _tailoring_context(
            request.user, request.data.get("job_id")
        )
        if error is not None:
            return error

        # The user's own key, decrypted here and now -- at the single moment it
        # is needed -- rather than held in memory for the session. Absent for a
        # keyless provider like Ollama, which simply ignores it.
        try:
            api_key = _user_api_key(request.user)
        except CredentialCryptoError:
            # reveal_key() has already dropped the undecryptable row, so the
            # UI will fall back to "not configured" and ask for a re-paste.
            return Response(
                {
                    "error": "Your saved API key could not be read and has been "
                              "removed. Please add it again in Settings.",
                    "code": "ai_key_unreadable",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            outcome = ResumeTailor.tailor_resume(
                resume=_stored_profile(master),
                job={
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "description": job.description,
                },
                # The match analysis already computed for this job, reused
                # rather than recomputed.
                match_analysis=job.match_result or {},
                jd_profile=jd_profile,
                api_key=api_key,
            )
        except AITailoringValidationError as exc:
            # Fabricated output is never returned as a suggestion. The
            # violations are returned so the UI can explain the rejection.
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

        payload = outcome.as_dict()
        payload["job"] = {
            "id": job.id,
            "title": job.title,
            "company": job.company,
        }
        payload["master_resume_id"] = master.id

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

        master, job, jd_profile, error = _tailoring_context(
            request.user, request.data.get("job_id")
        )
        if error is not None:
            return error

        raw_result = request.data.get("result")
        if not isinstance(raw_result, dict):
            return Response(
                {"error": "A tailoring result is required.", "code": "result_missing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Re-run the same normalisation and validation the service ran, against
        # our own copy of the master resume.
        parsed = normalise(raw_result)
        source = build_source_resume(_stored_profile(master))
        validation = validate_tailoring(parsed, source)

        if validation.rejected:
            return Response(
                {
                    "error": "This tailoring claims experience the master resume does "
                              "not support, so it was not saved.",
                    "code": "ai_validation_failed",
                    "violations": [v.as_dict() for v in validation.violations],
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        payload = parsed.to_dict()
        validation_payload = validation.as_dict()
        provider_name = request.data.get("provider") or ""

        tailored = Resume.objects.create(
            user=request.user,
            # Company + role reads naturally in the workspace and makes a
            # sensible download filename. The master name is deliberately not
            # folded in: it is already shown as the provenance link, and the
            # download filename strips parentheses anyway, which turned
            # "Acme - BE (Master Resume)" into "... BE Master Resume".
            name="%s - %s" % (job.company or "Job", job.title or "Role"),
            resume_type="TAILORED",
            is_master=False,
            source_resume=master,
            source_job=job,
                # The source view is re-derived from the stored master rather than
            # taken from the request, so a saved version is self-describing and
            # cannot be told to believe a client-supplied "original".
            tailoring_result={
                "result": payload,
                "validation": validation_payload,
                "source": source,
            },
            ai_provider=str(provider_name)[:50],
            # The structured content, so the existing resume endpoints can serve
            # this version without a document generator.
            profile_data=payload,
        )

        # Mirror the master's profile so a tailored resume is a normal resume to
        # the rest of the app. Deliberately the *full* master skill list, not
        # the emphasised subset: emphasis reorders in build_document, and
        # storing only the subset would silently drop every other skill from
        # the generated document.
        master_profile = _stored_profile(master)
        ResumeProfile.objects.update_or_create(
            resume=tailored,
            defaults={
                "skills": master_profile.get("skills") or [],
                "experience": master_profile.get("experience") or {},
                "education": master_profile.get("education") or "",
                "projects": master_profile.get("projects") or "",
                "certifications": master_profile.get("certifications") or "",
            },
        )

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
        described = factory.describe_provider()

        # Availability is per user, not global: the provider is configured
        # globally, but Gemini is unusable until *this* account has a key. The
        # button is therefore enabled per user, and the reason is specific
        # enough to act on ("add your key") instead of a generic outage.
        described["requires_user_key"] = bool(
            described.get("provider") == "gemini"
        )
        described["user_key_configured"] = ProviderCredential.objects.filter(
            user=request.user,
            provider="gemini",
        ).exists()

        return Response(described, status=status.HTTP_200_OK)


class ResumeDownloadView(APIView):
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
