FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY startup_ops_agent ./startup_ops_agent
COPY sample_data ./sample_data
COPY deploy ./deploy

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["uvicorn", "startup_ops_agent.api:app", "--host", "0.0.0.0", "--port", "8080"]
