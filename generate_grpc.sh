#!/bin/bash

# Generate gRPC client code from proto file
python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/sync_service.proto

echo "gRPC client code generated successfully!"
