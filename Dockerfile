FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN useradd --system --home /app --shell /usr/sbin/nologin crossbot \
    && mkdir -p /var/lib/crossbot \
    && chown crossbot:crossbot /var/lib/crossbot
USER crossbot

ENV CROSSBOT_DB_PATH=/var/lib/crossbot/crossbot.db
VOLUME ["/var/lib/crossbot"]
EXPOSE 9191

CMD ["python", "main.py"]
