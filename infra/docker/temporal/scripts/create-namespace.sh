#!/bin/sh
set -eu

namespace="${DEFAULT_NAMESPACE:-default}"
address="${TEMPORAL_ADDRESS:-temporal:7233}"
host="${address%:*}"
port="${address##*:}"
attempt=1
max_attempts="${TEMPORAL_HEALTH_CHECK_MAX_ATTEMPTS:-30}"

until nc -z -w 10 "$host" "$port" && temporal operator cluster health --address "$address"; do
  if [ "$attempt" -ge "$max_attempts" ]; then
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep "${TEMPORAL_HEALTH_CHECK_SLEEP_SECONDS:-5}"
done

if ! temporal operator namespace describe --namespace "$namespace" --address "$address" >/dev/null 2>&1; then
  temporal operator namespace create --namespace "$namespace" --address "$address"
fi
