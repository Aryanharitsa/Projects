set -eu
FILE="${REGISTRY_ADDRESS_FILE:-/blk/registry_address.txt}"
echo "[api] Waiting for registry file at $FILE ..."
i=0
while [ ! -s "$FILE" ]; do
  i=$((i+1))
  [ $i -gt 180 ] && { echo "[api] Timeout waiting for $FILE"; ls -l /blk || true; exit 1; }
  sleep 1
done
echo "[api] Found registry: $(cat "$FILE")"
exec uvicorn main:app --host 0.0.0.0 --port 8000
