# api stub image (spec 01 T6). Build context is the repository root:
#   docker build -f apps/api/Dockerfile .
FROM python:3.13-slim
WORKDIR /srv
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn>=0.30,<1" "pydantic>=2.7,<3" "pyyaml>=6" "jsonschema>=4" \
    "rfc3339-validator>=0.1.4,<1" tzdata "httpx>=0.27,<1" "psycopg[binary]>=3.2,<4" "pyjwt[crypto]>=2.8,<3"
COPY contracts ./contracts
COPY packages ./packages
COPY apps/api/app ./apps/api/app
ENV PYTHONPATH=/srv:/srv/packages:/srv/apps/api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
