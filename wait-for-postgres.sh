#!/bin/sh

set -e

host="$1"
shift
cmd="$@"

timeout=60
while ! pg_isready -h "$host" -U "postgres"; do
  if [ $timeout -le 0 ]; then
    echo "Postgres did not become ready in time."
    exit 1
  fi
  echo "Postgres is unavailable - sleeping"
  sleep 1
  timeout=$((timeout - 1))
done

>&2 echo "Postgres is up - executing command"
exec $cmd
