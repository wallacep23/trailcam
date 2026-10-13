# PostgreSQL 16 + pgvector 0.8 + PostGIS 3 (DESIGN §6, ADR 0002).
# Base: the official pgvector image (Debian, PGDG apt repo already configured); PostGIS from PGDG.
FROM pgvector/pgvector:0.8.0-pg16
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-postgis-3 postgresql-16-postgis-3-scripts \
 && rm -rf /var/lib/apt/lists/*
COPY docker/db/initdb/ /docker-entrypoint-initdb.d/
