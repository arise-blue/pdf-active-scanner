#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
python3 tests/make_samples.py

python3 pdf_active_scanner.py tests/samples/malicious_openaction.pdf
python3 pdf_active_scanner.py tests/samples/legit_form_js.pdf

if python3 pdf_active_scanner.py tests/samples/malicious_openaction.pdf; then
  echo "expected malicious_openaction.pdf to be blocked" >&2
  exit 1
fi

if python3 pdf_active_scanner.py tests/samples/malicious_launch.pdf; then
  echo "expected malicious_launch.pdf to be blocked" >&2
  exit 1
fi

python3 pdf_active_scanner.py --json tests/samples/legit_form_js.pdf >/dev/null
echo "tests passed"
