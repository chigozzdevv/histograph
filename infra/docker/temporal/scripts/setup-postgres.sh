#!/bin/sh
set -eu

: "${POSTGRES_SEEDS:?POSTGRES_SEEDS is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PWD:?POSTGRES_PWD is required}"

database_exists() {
  PGPASSWORD="$POSTGRES_PWD" psql \
    --host "$POSTGRES_SEEDS" \
    --port "${DB_PORT:-5432}" \
    --username "$POSTGRES_USER" \
    --dbname postgres \
    --tuples-only \
    --no-align \
    --command "SELECT 1 FROM pg_database WHERE datname = '$1'" | grep -q 1
}

schema_exists() {
  PGPASSWORD="$POSTGRES_PWD" psql \
    --host "$POSTGRES_SEEDS" \
    --port "${DB_PORT:-5432}" \
    --username "$POSTGRES_USER" \
    --dbname "$1" \
    --tuples-only \
    --no-align \
    --command "SELECT to_regclass('public.schema_version') IS NOT NULL" | grep -q t
}

configure_database() {
  database="$1"
  schema_path="$2"

  if ! database_exists "$database"; then
    temporal-sql-tool \
      --plugin postgres12 \
      --ep "$POSTGRES_SEEDS" \
      -u "$POSTGRES_USER" \
      -p "${DB_PORT:-5432}" \
      --db "$database" \
      create
  fi

  if ! schema_exists "$database"; then
    temporal-sql-tool \
      --plugin postgres12 \
      --ep "$POSTGRES_SEEDS" \
      -u "$POSTGRES_USER" \
      -p "${DB_PORT:-5432}" \
      --db "$database" \
      setup-schema \
      -v 0.0
  fi

  temporal-sql-tool \
    --plugin postgres12 \
    --ep "$POSTGRES_SEEDS" \
    -u "$POSTGRES_USER" \
    -p "${DB_PORT:-5432}" \
    --db "$database" \
    update-schema \
    -d "$schema_path"
}

until nc -z -w 10 "$POSTGRES_SEEDS" "${DB_PORT:-5432}"; do
  sleep 2
done

configure_database temporal /etc/temporal/schema/postgresql/v12/temporal/versioned
configure_database temporal_visibility /etc/temporal/schema/postgresql/v12/visibility/versioned
