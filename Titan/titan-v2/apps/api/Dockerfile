FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY abi.json .
CMD ["/bin/sh","-lc","FILE=${REGISTRY_ADDRESS_FILE:-/blk/registry_address.txt}; echo \"[api] waiting for $FILE ...\"; for i in $(seq 1 180); do [ -s \"$FILE\" ] && break; sleep 1; done; [ -s \"$FILE\" ] || { echo \"[api] timeout waiting for $FILE\"; ls -l /blk || true; exit 1; }; echo \"[api] Found registry: $(cat $FILE)\"; exec uvicorn main:app --host 0.0.0.0 --port 8000"]
