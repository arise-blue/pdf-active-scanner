FROM python:3.12-slim

RUN useradd --create-home --shell /usr/sbin/nologin scanner
WORKDIR /scanner

COPY pdf_active_scanner.py /scanner/pdf_active_scanner.py

USER scanner
ENTRYPOINT ["python", "/scanner/pdf_active_scanner.py"]
