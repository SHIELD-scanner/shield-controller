FROM python:3.13-alpine

WORKDIR /app


RUN apk update
RUN apk upgrade
RUN rm -rf /var/cache/apk/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generate gRPC code
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/sync_service.proto


# Create non-root user for security
RUN addgroup -g 1001 -S appgroup && \
    adduser -u 1001 -S appuser -G appgroup

# Change ownership of app directory to non-root user
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

CMD ["python", "sync_controller.py"]
