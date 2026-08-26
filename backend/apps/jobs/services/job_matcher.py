from apps.resumes.services.parser import ResumeParser
from apps.resumes.services.resume_profile import ResumeProfile

from .jd_profile import JDProfile
from .match_engine import MatchEngine


class JobMatcher:

    @staticmethod
    def match(job, resume_path):
        # 1. Extract resume text
        resume_text = ResumeParser.extract_text(resume_path)

        # 2. Build resume profile
        resume_profile = ResumeProfile.build(resume_text)

        # 3. Build JD profile
        jd_profile = JDProfile.build(job.description)

        # 4. Calculate match
        result = MatchEngine.calculate(
            resume_profile,
            jd_profile,
        )

        # 5. Save result on Job
        job.match_score = result["score"]
        job.decision = result["decision"]
        job.status = "READY"
        job.save(
            update_fields=[
                "match_score",
                "decision",
                "status",
                "updated_at",
            ]
        )

        return result