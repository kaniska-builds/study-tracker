
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

SOURCES = {
    "Mathematics": (
        "https://cbseacademic.nic.in/web_material/"
        "CurriculumMain27/SecPart1/Maths_SecP1X_2026-27.pdf"
    ),
    "Social Science": (
        "https://cbseacademic.nic.in/web_material/"
        "CurriculumMain27/SecPart1/"
        "SocialScience_SecP1X_2026-27.pdf"
    ),
}

MAX_PDF_BYTES = 25 * 1024 * 1024
MIN_TEXT_CHARS = 200
OUTPUT = Path("draft-output")
OUTPUT.mkdir(parents=True, exist_ok=True)

report = {
    "purpose": "Draft extraction only; never publish automatically.",
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "status": "review_required",
    "documents": [],
}

for subject, url in SOURCES.items():
    item = {
        "subject": subject,
        "source": url,
        "status": "error",
        "textFile": None,
        "warnings": [],
    }

    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "StudyTracker-SyllabusReview/1.0"},
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            final_url = response.geturl()

            if final_url != url:
                raise ValueError("Unexpected redirect; manual review required.")

            data = response.read(MAX_PDF_BYTES + 1)

        if len(data) > MAX_PDF_BYTES:
            raise ValueError("PDF exceeds the 25 MB safety limit.")

        if not data.startswith(b"%PDF"):
            raise ValueError("Downloaded content is not a valid PDF.")

        reader = PdfReader(BytesIO(data), strict=True)

        if reader.is_encrypted:
            raise ValueError("PDF is encrypted; manual review required.")

        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append({
                "page": page_number,
                "text": text,
            })

        combined = "\n\n".join(
            f"--- PAGE {page['page']} ---\n{page['text']}"
            for page in pages
        )

        digest = hashlib.sha256(data).hexdigest()
        text_path = OUTPUT / (
            subject.lower().replace(" ", "-") + "-draft.txt"
        )

        text_path.write_text(combined, encoding="utf-8")

        item.update({
            "status": "extracted_for_review",
            "sha256": digest,
            "pdfBytes": len(data),
            "pageCount": len(pages),
            "extractedCharacters": len(combined),
            "textFile": str(text_path),
        })

        if len(combined.strip()) < MIN_TEXT_CHARS:
            item["status"] = "manual_review_required"
            item["warnings"].append(
                "Very little text extracted; PDF may be scanned or unsupported."
            )

        if any(not page["text"].strip() for page in pages):
            item["warnings"].append(
                "One or more pages have no extractable text; check manually."
            )

    except Exception as exc:
        item["warnings"].append(
            f"{type(exc).__name__}: {str(exc)[:300]}"
        )

    report["documents"].append(item)

report_path = OUTPUT / "extraction-report.json"
report_path.write_text(
    json.dumps(report, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

print(json.dumps(report, indent=2, ensure_ascii=False))

if any(item["status"] == "error" for item in report["documents"]):
    raise SystemExit("One or more PDFs failed. Review the report artifact.")
                                    
