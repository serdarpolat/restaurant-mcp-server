FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_URL=sqlite:////data/restaurant.db

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install . \
    && useradd --create-home app \
    && mkdir /data && chown app /data

USER app
VOLUME /data
EXPOSE 8000 8001

# Seeds demo data on first start, then serves the POS API.
CMD ["restaurant-pos-api", "--host", "0.0.0.0"]
