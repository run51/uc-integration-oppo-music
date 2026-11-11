# OPPO Music integration for the Unfolded Circle Remote — Docker image.
# Run it with host networking so the remote can discover it (mDNS) and reach its WebSocket port.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UC_CONFIG_HOME=/config \
    UC_INTEGRATION_HTTP_PORT=9095 \
    UC_LOG_LEVEL=INFO

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY driver.json .
COPY intg-oppo-music ./intg-oppo-music

VOLUME ["/config"]
EXPOSE 9095

# driver.json is looked up in the working directory
CMD ["python", "intg-oppo-music/driver.py"]
