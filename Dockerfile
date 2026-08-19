FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl nodejs npm && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

COPY dashboard/ ./dashboard/
RUN cd dashboard && npm install && npm run build

EXPOSE 8000
CMD ["uvicorn", "src.hireagent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
