# Debian-slim statt Alpine: die Wheels für Pillow und fonttools, die fpdf2
# für die PDF-Erzeugung braucht, sind dort ohne Compiler verfügbar. Der
# Aufpreis von rund 70 MB Image ist die deutlich robustere Wahl.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Berlin \
    SCOPEX_DATABASE_URL=sqlite:////data/scopex.db

WORKDIR /opt/scopex

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 8099
CMD ["/run.sh"]
