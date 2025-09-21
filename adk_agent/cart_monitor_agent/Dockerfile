FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

RUN adduser --uid 1001 --disabled-password --gecos "" appuser
USER appuser

COPY requirements.txt .
RUN pip install --user -r requirements.txt

COPY --chown=appuser:appuser agent.py .

ENV PATH="/home/appuser/.local/bin:${PATH}"
EXPOSE 10102
CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "10102"]
