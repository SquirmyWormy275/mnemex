FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system mnemex && adduser --system --ingroup mnemex mnemex

COPY . /app

RUN python -m pip install . && \
    DJANGO_SETTINGS_MODULE=mnemex.web.settings.build \
    python manage.py collectstatic --noinput && \
    chown -R mnemex:mnemex /app

USER mnemex

CMD ["gunicorn", "mnemex.web.wsgi:application", "--bind", "0.0.0.0:8000"]
