FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    BATTLEZONE_NET_MODE=server \
    BATTLEZONE_NET_HOST=0.0.0.0 \
    BATTLEZONE_NET_PORT=51515 \
    BATTLEZONE_SERVER_UI=logs \
    BATTLEZONE_SERVER_LOG_INTERVAL=5 \
    BATTLEZONE_SERVER_WINDOW=minimized \
    ALSOFT_DRIVERS=null

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xvfb \
        xauth \
        libegl1 \
        libgl1 \
        libglib2.0-0 \
        libx11-6 \
        libxcursor1 \
        libxrandr2 \
        libxinerama1 \
        libxi6 \
        libxrender1 \
        libxext6 \
        libopenal1 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config ./config
COPY models ./models
COPY sfx ./sfx
COPY battlezone ./battlezone
COPY test02.py README.md ./

EXPOSE 51515/udp

CMD ["sh", "-c", "xvfb-run -a -s '-screen 0 720x405x24' python -m battlezone.server"]
