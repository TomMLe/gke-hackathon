FROM python:3.13-slim
WORKDIR /app

RUN adduser --uid 1001 --disabled-password --gecos "" myuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY cart_monitor_agent ./cart_monitor_agent
COPY recommend_agent ./recommend_agent
COPY orchestrator_agent ./orchestrator_agent
COPY common ./common

RUN chown -R myuser:myuser /app
USER myuser

ENV PATH="/home/myuser/.local/bin:$PATH"

CMD ["sh", "-c", "python -m $AGENT_MODULE --port $PORT"]
