#!/bin/sh
set -e

if [ "$RUN_MIGRATIONS" = "true" ]; then
    python manage.py migrate --noinput
fi

if [ "$RUN_COLLECTSTATIC" = "true" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
