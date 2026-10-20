FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    FLY_HOST=0.0.0.0 \
    FLY_PORT=7860 \
    FLY_DATA=/data \
    FLY_UPLOADS=/data/uploads \
    MPLBACKEND=Agg \
    NUMBA_CACHE_DIR=/data/numba_cache

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      "numpy>=1.26" "scipy>=1.11" "pandas>=2.0" "pyarrow>=14" \
      "matplotlib>=3.8" "pillow>=10" "numba>=0.59" "flask>=3.0"

WORKDIR /app
RUN git clone --depth 1 https://github.com/opendeta/fly-semulator /app

# MaleCNS data (CC-BY, ~535 MB) + compact graph + plasticity substrate
RUN mkdir -p /data && bash scripts/fetch_data.sh && python3 scripts/build_plasticity.py

# keys: override these in the Space settings (Settings -> Variables and secrets)
ENV FLY_USER=fly \
    FLY_PW=changeme \
    FLY_KEY=changeme-control \
    FLY_VIEW_KEY=changeme-view

EXPOSE 7860
CMD ["python3", "scripts/webapp.py"]
