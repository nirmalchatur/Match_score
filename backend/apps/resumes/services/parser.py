from pathlib import Path

from pypdf import PdfReader


class ResumeParser:

    @staticmethod
    def extract_text(file) -> str:
        """
        Extract text from a resume.

        Supports:
        - filesystem path
        - Django FileField / UploadedFile
        """

        # Django FileField / UploadedFile
        if hasattr(file, "open"):
            file.open("rb")

            try:
                reader = PdfReader(file)

                pages = []

                for page in reader.pages:
                    text = page.extract_text()

                    if text:
                        pages.append(text)

                return "\n".join(pages).strip()

            finally:
                file.close()

        # Normal filesystem path
        path = Path(file)

        if not path.exists():
            raise FileNotFoundError(
                f"Resume file not found: {file}"
            )

        reader = PdfReader(str(path))

        pages = []

        for page in reader.pages:
            text = page.extract_text()

            if text:
                pages.append(text)

        return "\n".join(pages).strip()