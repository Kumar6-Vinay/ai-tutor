FROM python:3.13-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENV TUTOR_DB=/data/tutor.db
RUN useradd -r tutor && mkdir -p /data && chown tutor /data && chmod +x /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
# Starts as root only to fix ownership of a mounted data disk, then drops to the unprivileged user.
ENTRYPOINT ["docker-entrypoint.sh"]
