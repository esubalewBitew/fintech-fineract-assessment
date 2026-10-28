#!/bin/bash
# Dedicated app DB owners (least privilege). Postgres 15+ requires ownership
# (or explicit grants) to CREATE on public — do not connect apps as root.
set -e
export PGPASSWORD=$POSTGRES_PASSWORD
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mock_erp') THEN
      CREATE USER mock_erp WITH PASSWORD 'mock_erp_secret';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'integration') THEN
      CREATE USER integration WITH PASSWORD 'integration_secret';
    END IF;
  END
  \$\$;

  SELECT 'CREATE DATABASE mock_erp OWNER mock_erp'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mock_erp')\gexec
  SELECT 'CREATE DATABASE integration OWNER integration'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'integration')\gexec

  ALTER DATABASE mock_erp OWNER TO mock_erp;
  ALTER DATABASE integration OWNER TO integration;
EOSQL
