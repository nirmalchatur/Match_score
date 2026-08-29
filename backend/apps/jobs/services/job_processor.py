from apps.jobs.models import Job
from apps.jobs.services.jd_profile import JDProfile
from apps.jobs.services.match_engine import MatchEngine
from apps.resumes.models import Resume


class JobProcessor:

    @staticmethod
    def process(job_data):

        # Get master resume
        resume = Resume.objects.get(
            is_master=True
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

        # Save/update Job
        job, created = Job.objects.update_or_create(
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