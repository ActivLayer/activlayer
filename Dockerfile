FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACTIVLAYER_HOME=/data

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 activlayer \
    && mkdir -p /data \
    && chown -R activlayer:activlayer /data

USER activlayer
VOLUME ["/data"]
EXPOSE 8787

CMD ["activlayer", "serve", "--host", "0.0.0.0", "--port", "8787"]

