-- Runs once, when the data volume is first created.
-- The app database gets its extensions from the Alembic migration; the test database is created
-- here so `pytest` can run against the same container (TRAILCAM_TEST_DATABASE_URL).
CREATE DATABASE trailcam_test;
\connect trailcam_test
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
\connect trailcam
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
