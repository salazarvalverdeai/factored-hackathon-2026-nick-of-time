# api image (spec 01 T6, spec 05). Build context is the repository root:
#   docker build -f apps/api/Dockerfile .
FROM python:3.13-slim
WORKDIR /srv
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn>=0.30,<1" "pydantic>=2.7,<3" "pyyaml>=6" "jsonschema>=4" \
    "rfc3339-validator>=0.1.4,<1" tzdata "httpx>=0.27,<1" "psycopg[binary]>=3.2,<4" "pyjwt[crypto]>=2.8,<3" \
    "alembic>=1.13,<2" "sqlalchemy>=2,<3" "duckdb>=1.1" "boto3>=1.35"
COPY contracts ./contracts
COPY packages ./packages
COPY apps/api/app ./apps/api/app
COPY eval/demo/customers.json eval/demo/sample_cases.jsonl ./eval/demo/
# the dev cases tag the demo scenarios (D-068); the held-out set never enters the image (spec 09)
COPY eval/cases/dev.jsonl ./eval/cases/dev.jsonl
# demo type D calls S1 (Haiku 4.5) through nick_of_time.llm, which prices every call from these rows (D-058)
COPY eval/bench/arms.yaml eval/bench/prices.yaml ./eval/bench/
COPY apps/api/alembic.ini apps/api/migrate.sh ./apps/api/
COPY apps/api/migrations ./apps/api/migrations
# infra/deploy.sh runs /app/migrate.sh once before `up` (spec 06 FR-04)
RUN mkdir -p /app && ln -s /srv/apps/api/migrate.sh /app/migrate.sh && chmod +x /srv/apps/api/migrate.sh
ENV PYTHONPATH=/srv:/srv/packages:/srv/apps/api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
