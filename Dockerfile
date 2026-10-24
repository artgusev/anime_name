FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV LISTEN_HOST=0.0.0.0 \
    LISTEN_PORT=8080 \
    UPSTREAM_URL=http://prowlarr:9696 \
    PYTHONUNBUFFERED=1

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

CMD ["animename", "serve"]
