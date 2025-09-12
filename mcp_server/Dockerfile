FROM python:3.13-slim
WORKDIR /app

RUN adduser --uid 999 --disabled-password --gecos "" myuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R myuser:myuser /app
USER myuser

CMD ["python", "./ob_mcp.py"]
