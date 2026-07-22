FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /opt/application \
    && ln -s /app/entrypoint.sh /opt/application/run.sh \
    && addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app --home /app --no-create-home app \
    && chown -R app:app /app /opt/application

EXPOSE 8000
USER app
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/docs', timeout=3)" || exit 1
ENTRYPOINT ["/app/entrypoint.sh"]
