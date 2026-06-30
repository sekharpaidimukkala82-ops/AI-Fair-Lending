-- Fair Lending Platform — PostgreSQL initialization
-- This runs once when the Postgres container is first created.
-- SQLAlchemy handles the actual table creation via init_db().

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- trigram index for text search

-- Ensure the fairlend user owns the database
GRANT ALL PRIVILEGES ON DATABASE fairlending TO fairlend;
