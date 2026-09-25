from apps.jobs.models import Job
from apps.jobs.services.jd_profile import JDProfile
from apps.jobs.services.match_engine import MatchEngine
from apps.resumes.models import Resume


class JobProcessor:

    @staticmethod
    def process(job_data, user):
        """
        Run the analysis pipeline for a single account.

        Both the master resume lookup and the Job upsert are scoped to
        `user`, so one account can never score against another account's
        resume, nor overwrite another account's saved job.
        """

        # Get this account's master resume
        resume = Resume.objects.get(
            user=user,
            is_master=True,
        )

        # Get structured resume profile
        resume_profile_model = resume.profile

        if not resume_profile_model:
            raise ValueError(
                "Master resume profile not found"
            )

        # Convert database model to dictionary
        resume_profile = {
            "skills": resume_profile_model.skills,
            "experience": resume_profile_model.experience,
            "education": resume_profile_model.education,
            "projects": resume_profile_model.projects,
            "certifications": (
                resume_profile_model.certifications
            ),
        }

        # Build JD profile
        jd_profile = JDProfile.build(
            job_data.description
        )

        # Calculate match
        result = MatchEngine.calculate(
            resume_profile,
            jd_profile,
        )

        # Save/update Job (scoped to the owner)
        job, created = Job.objects.update_or_create(
            user=user,
            url=job_data.url,
            defaults={
                "company": job_data.company,
                "title": job_data.title,
                "location": job_data.location,
                "description": job_data.description,
                "match_score": result["score"],
                "match_result": result,
                "decision": result["decision"],
                "status": "READY",
            },
        )

        return job, result, created