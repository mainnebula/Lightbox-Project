FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ".[gui]"

# Store sessions in a volume-mountable directory
ENV LIGHTBOX_DIR=/data
VOLUME /data

EXPOSE 8780

CMD ["lightbox", "gui", "--host", "0.0.0.0", "--no-browser"]
