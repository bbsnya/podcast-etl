#!/bin/bash
# Отдельные БД для метаданных Airflow и Metabase (DWH остаётся в $POSTGRES_DB).
# Выполняется только при первом старте с пустым томом postgres_data.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE DATABASE airflow_db;
CREATE DATABASE metabase_db;
EOSQL
