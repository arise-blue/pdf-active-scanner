#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


BLOCKING_PDF_NAMES = {
    b"/Launch": "launch action can execute external programs",
    b"/EmbeddedFile": "embedded file attachment can hide a payload",
    b"/RichMedia": "rich media can contain active embedded content",
    b"/SubmitForm": "form submission can exfiltrate document data",
    b"/GoToE": "embedded-file navigation can trigger attached content",
    b"/GoToR": "remote document navigation can chain to external content",
    b"/ImportData": "import-data action can load external form data",
    b"/Rendition": "rendition action can trigger multimedia content",
}

ACTIVE_PDF_NAMES = {
    b"/JavaScript",
    b"/JS",
    b"/OpenAction",
    b"/AA",
    b"/AcroForm",
    b"/XFA",
    b"/URI",
}

JS_DANGEROUS_PATTERNS = {
    r"\bapp\.launchURL\s*\(": "opens an external URL",
    r"\bthis\.submitForm\s*\(": "submits form data externally",
    r"\bthis\.getURL\s*\(": "opens an external URL",
    r"\butil\.printf\s*\(": "historically abused Acrobat JavaScript API",
    r"\bCollab\b": "historically abused Acrobat collaboration API",
    r"\bSOAP\b": "network-capable Acrobat SOAP API",
    r"\bNet\.HTTP\b": "network-capable Acrobat API",
    r"\bDoc\.getField\s*\([^)]*\)\.browseForFileToSubmit\s*\(": "prompts for local file submission",
    r"\beval\s*\(": "dynamic code execution",
    r"\bFunction\s*\(": "dynamic code execution",
    r"\bunescape\s*\(": "common JavaScript obfuscation primitive",
    r"%u[0-9a-fA-F]{4}": "escaped unicode shellcode-like data",
    r"(?:\\x[0-9a-fA-F]{2}){8,}": "hex-escaped JavaScript payload",
}

JS_LEGIT_FORM_PATTERNS = {
    r"\bAFNumber_Format\s*\(",
    r"\bAFNumber_Keystroke\s*\(",
    r"\bAFPercent_Format\s*\(",
    r"\bAFPercent_Keystroke\s*\(",
    r"\bAFDate_Format(?:Ex)?\s*\(",
    r"\bAFDate_Keystroke(?:Ex)?\s*\(",
    r"\bAFTime_Format(?:Ex)?\s*\(",
    r"\bAFTime_Keystroke(?:Ex)?\s*\(",
    r"\bAFSpecial_Format\s*\(",
    r"\bAFSpecial_Keystroke\s*\(",
    r"\bAFRange_Validate\s*\(",
    r"\bAFSimple_Calculate\s*\(",
    r"\bAFMakeNumber\s*\(",
    r"\bevent\.(?:value|rc|target|change|willCommit|selStart|selEnd)\b",
    r"\bthis\.getField\s*\(",
}

SAFE_FORM_CONTEXT_NAMES = {
    b"/AcroForm",
    b"/Widget",
    b"/Tx",
    b"/Btn",
    b"/Ch",
    b"/Keystroke",
    b"/Validate",
    b"/Calculate",
    b"/Format",
    b"/Fo",
    b"/Bl",
}


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    offset: int | None = None
    sample: str | None = None


def pdf_unescape_string(value: bytes) -> str:
    out = bytearray()
    i = 0
    while i < len(value):
        c = value[i]
        if c == 0x5C and i + 1 < len(value):
            nxt = value[i + 1]
            escapes = {
                ord("n"): b"\n",
                ord("r"): b"\r",
                ord("t"): b"\t",
                ord("b"): b"\b",
                ord("f"): b"\f",
                ord("("): b"(",
                ord(")"): b")",
                ord("\\"): b"\\",
            }
            if nxt in escapes:
                out.extend(escapes[nxt])
                i += 2
                continue
            if 48 <= nxt <= 55:
                octal = bytes([nxt])
                j = i + 2
                while j < min(i + 4, len(value)) and 48 <= value[j] <= 55:
                    octal += bytes([value[j]])
                    j += 1
                out.append(int(octal, 8) & 0xFF)
                i = j
                continue
            if nxt in (ord("\n"), ord("\r")):
                i += 2
                if nxt == ord("\r") and i < len(value) and value[i] == ord("\n"):
                    i += 1
                continue
        out.append(c)
        i += 1
    return out.decode("utf-8", errors="replace")


def decode_hex_string(value: bytes) -> str:
    cleaned = re.sub(rb"\s+", b"", value)
    if len(cleaned) % 2:
        cleaned += b"0"
    try:
        return bytes.fromhex(cleaned.decode("ascii")).decode("utf-8", errors="replace")
    except ValueError:
        return ""


def iter_pdf_strings(content: bytes) -> Iterable[tuple[int, str]]:
    i = 0
    while i < len(content):
        if content[i] == ord("("):
            start = i
            depth = 1
            escaped = False
            i += 1
            buf = bytearray()
            while i < len(content) and depth:
                c = content[i]
                if escaped:
                    buf.append(0x5C)
                    buf.append(c)
                    escaped = False
                elif c == 0x5C:
                    escaped = True
                elif c == ord("("):
                    depth += 1
                    buf.append(c)
                elif c == ord(")"):
                    depth -= 1
                    if depth:
                        buf.append(c)
                else:
                    buf.append(c)
                i += 1
            yield start, pdf_unescape_string(bytes(buf))
            continue
        if content[i] == ord("<") and i + 1 < len(content) and content[i + 1] != ord("<"):
            start = i
            end = content.find(b">", i + 1)
            if end != -1:
                raw = content[i + 1:end]
                if re.fullmatch(rb"[\s0-9a-fA-F]*", raw):
                    decoded = decode_hex_string(raw)
                    if decoded:
                        yield start, decoded
                i = end + 1
                continue
        i += 1


def flate_streams(content: bytes) -> Iterable[tuple[int, bytes]]:
    stream_re = re.compile(rb"<<(?P<dict>.*?)>>\s*stream\r?\n(?P<data>.*?)\r?\nendstream", re.S)
    for match in stream_re.finditer(content):
        dictionary = match.group("dict")
        if b"/FlateDecode" not in dictionary:
            continue
        data = match.group("data")
        try:
            yield match.start(), zlib.decompress(data)
        except zlib.error:
            yield match.start(), data


def extract_javascript_candidates(content: bytes) -> list[tuple[int, str, bytes]]:
    expanded = [(0, content)] + list(flate_streams(content))
    candidates: list[tuple[int, str, bytes]] = []
    for base_offset, data in expanded:
        for marker in (b"/JS", b"/JavaScript"):
            for match in re.finditer(re.escape(marker), data):
                window = data[match.start() : match.start() + 5000]
                for str_offset, text in iter_pdf_strings(window):
                    if looks_like_javascript(text):
                        context = data[max(0, match.start() - 700) : match.start() + 700]
                        candidates.append((base_offset + match.start() + str_offset, text, context))
                        break
    return candidates


def looks_like_javascript(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "function",
            "event.",
            "this.",
            "app.",
            "afnumber_",
            "afdate_",
            "afsimple_",
            "submitform",
            "launchurl",
            "eval(",
        )
    )


def is_likely_legit_form_js(script: str, context: bytes) -> bool:
    if any(re.search(pattern, script, re.I) for pattern in JS_DANGEROUS_PATTERNS):
        return False
    has_form_context = any(name in context for name in SAFE_FORM_CONTEXT_NAMES)
    has_form_api = any(re.search(pattern, script, re.I) for pattern in JS_LEGIT_FORM_PATTERNS)
    has_external_target = re.search(r"https?://|file:|mailto:|\\\\|/[A-Za-z]:", script, re.I)
    return has_form_context and has_form_api and not has_external_target


def scan_pdf(path: Path) -> dict:
    content = path.read_bytes()
    findings: list[Finding] = []
    sha256 = hashlib.sha256(content).hexdigest()

    if not content.startswith(b"%PDF-"):
        findings.append(Finding("malicious", "not_pdf", "file does not start with a PDF header"))
        return result(path, sha256, content, findings)

    expanded_blobs = [(0, content)] + list(flate_streams(content))
    for base_offset, blob in expanded_blobs:
        for name, reason in BLOCKING_PDF_NAMES.items():
            for match in re.finditer(re.escape(name), blob):
                findings.append(
                    Finding("malicious", "blocked_pdf_action", reason, base_offset + match.start(), name.decode())
                )

        for open_action in re.finditer(rb"/OpenAction", blob):
            action_window = blob[open_action.start() : open_action.start() + 1200]
            if b"/JS" in action_window or b"/JavaScript" in action_window:
                findings.append(
                    Finding(
                        "malicious",
                        "auto_open_javascript",
                        "document contains JavaScript reachable from /OpenAction",
                        base_offset + open_action.start(),
                        "/OpenAction",
                    )
                )

        if b"/AA" in blob and (b"/JS" in blob or b"/JavaScript" in blob):
            findings.append(
                Finding(
                    "info",
                    "additional_action_javascript",
                    "document contains JavaScript in an additional-action event",
                    base_offset + blob.find(b"/AA"),
                    "/AA",
                )
            )

        for name in ACTIVE_PDF_NAMES:
            if name in blob:
                findings.append(
                    Finding("info", "active_pdf_element", f"active PDF element present: {name.decode()}", base_offset + blob.find(name), name.decode())
                )

    seen_scripts = set()
    for offset, script, context in extract_javascript_candidates(content):
        script_key = (offset, compact(script, 500))
        if script_key in seen_scripts:
            continue
        seen_scripts.add(script_key)
        if is_likely_legit_form_js(script, context):
            findings.append(
                Finding(
                    "allowed",
                    "legitimate_form_javascript",
                    "form-scoped JavaScript matches common formatting, validation, or calculation behavior",
                    offset,
                    compact(script),
                )
            )
            continue

        matched = False
        for pattern, reason in JS_DANGEROUS_PATTERNS.items():
            if re.search(pattern, script, re.I | re.S):
                findings.append(Finding("malicious", "dangerous_javascript", reason, offset, compact(script)))
                matched = True
        if not matched:
            findings.append(
                Finding(
                    "suspicious",
                    "unknown_javascript",
                    "JavaScript is present but does not match the safe form allowlist",
                    offset,
                    compact(script),
                )
            )

    return result(path, sha256, content, findings)


def compact(value: str, limit: int = 220) -> str:
    squashed = re.sub(r"\s+", " ", value).strip()
    return squashed[: limit - 3] + "..." if len(squashed) > limit else squashed


def result(path: Path, sha256: str, content: bytes, findings: list[Finding]) -> dict:
    worst = "clean"
    if any(f.severity == "malicious" for f in findings):
        worst = "blocked"
    elif any(f.severity == "suspicious" for f in findings):
        worst = "review"
    return {
        "file": str(path),
        "sha256": sha256,
        "size": len(content),
        "verdict": worst,
        "summary": {
            "malicious": sum(1 for f in findings if f.severity == "malicious"),
            "suspicious": sum(1 for f in findings if f.severity == "suspicious"),
            "allowed": sum(1 for f in findings if f.severity == "allowed"),
            "info": sum(1 for f in findings if f.severity == "info"),
        },
        "findings": [asdict(f) for f in findings],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan PDFs for JavaScript and embedded active elements.")
    parser.add_argument("pdf", nargs="+", type=Path, help="PDF file(s) to scan")
    parser.add_argument("--json", action="store_true", help="write machine-readable JSON")
    parser.add_argument("--strict-review", action="store_true", help="exit 2 for suspicious files that need review")
    parser.add_argument("--allow-review", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    results = []
    exit_code = 0
    for pdf in args.pdf:
        scan = scan_pdf(pdf)
        results.append(scan)
        if scan["verdict"] == "blocked" or (scan["verdict"] == "review" and args.strict_review):
            exit_code = 2

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    else:
        for scan in results:
            print(f"{scan['file']}: {scan['verdict'].upper()}")
            print(f"  sha256: {scan['sha256']}")
            for finding in scan["findings"]:
                if finding["severity"] == "info":
                    continue
                at = f" at offset {finding['offset']}" if finding["offset"] is not None else ""
                print(f"  - {finding['severity']}: {finding['message']}{at}")
                if finding["sample"]:
                    print(f"    sample: {finding['sample']}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
