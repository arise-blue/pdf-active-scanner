# PDF Active Content Scanner

Dockerized PDF scanner for JavaScript and embedded active elements.

The scanner blocks clearly dangerous active PDF behavior such as `/Launch`, embedded files, rich media, auto-open JavaScript, form submission, external URL APIs, dynamic JavaScript execution, and common obfuscation patterns.

It allows common form-scoped Acrobat JavaScript when it is attached to form/widget context and only appears to perform formatting, keystroke validation, field validation, or calculations.

## Build

```sh
docker build -t pdf-active-scanner:local .
```

## Run With Docker

Mount the directory containing PDFs read-only and pass PDF paths inside the container:

```sh
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  -v "$PWD/..:/scan:ro" \
  pdf-active-scanner:local /scan/Sample-Fillable-PDF.pdf
```

JSON output:

```sh
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  -v "$PWD/..:/scan:ro" \
  pdf-active-scanner:local --json /scan/Sample-Fillable-PDF.pdf
```

## Run With Compose

```sh
docker compose run --rm pdf-scanner /scan/Sample-Fillable-PDF.pdf
```

## Run Locally

```sh
python3 pdf_active_scanner.py ../Sample-Fillable-PDF.pdf
```

## Exit Codes

- `0`: clean, or only allowed legitimate form JavaScript.
- `0`: suspicious but unconfirmed JavaScript requiring review.
- `2`: blocked malicious content.

Use `--strict-review` if suspicious but unclassified JavaScript should fail CI.

## Security Notes

Static PDF JavaScript classification is heuristic. This tool is designed for gateway and CI checks, not as a complete malware sandbox. Keep the container network disabled and treat `review` as blocked unless a human has validated the PDF source and behavior.
