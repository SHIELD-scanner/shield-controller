# Shield Controller gRPC Architecture

## Overview

The Shield Controller has been updated to use a gRPC-based architecture. Instead of directly connecting to MongoDB, the controller now sends data to a gRPC receiver service that handles the MongoDB operations.

## Architecture Changes

### Before (Direct MongoDB)
```
Shield Controller → MongoDB
```

### After (gRPC)
```
Shield Controller → gRPC Receiver Service → MongoDB
```

## Benefits

1. **Decoupling**: The controller is no longer tightly coupled to MongoDB
2. **Scalability**: The receiver service can be scaled independently
3. **Flexibility**: Easier to switch database backends or add data processing
4. **Security**: Database credentials only needed in the receiver service

## Configuration

### Environment Variables (.env file)

The controller uses a `.env` file for configuration. Copy `.env.example` to `.env` and update the values:

```bash
cp .env.example .env
```

The controller now uses these environment variables:

- `GRPC_SERVER_HOST`: Hostname of the gRPC receiver service (default: `localhost`)
- `GRPC_SERVER_PORT`: Port of the gRPC receiver service (default: `50051`)
- `CLUSTER`: Cluster name (optional, auto-detected if not provided)
- `LOG_LEVEL`: Logging level (default: `info`)
- `DSN`: Sentry DSN for error tracking (optional)

### Migration from MongoDB Config

If you're migrating from the MongoDB version, update your `.env` file:

**Remove or comment out these variables:**
```bash
# MONGO_URI=mongodb://...
# MONGO_DB=shield
```

**Add these new variables:**
```bash
GRPC_SERVER_HOST=grpc-receiver-service
GRPC_SERVER_PORT=50051
```

## Development

### Generating gRPC Code

To regenerate the gRPC client code after modifying the proto file:

```bash
./generate_grpc.sh
```

Or manually:

```bash
python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/sync_service.proto
```

### Proto File

The gRPC service definition is in `proto/sync_service.proto`. It defines two main operations:

1. `SyncResource`: For syncing Kubernetes custom resources
2. `SyncNamespace`: For syncing Kubernetes namespaces

## gRPC Receiver Service

You'll need to implement a gRPC receiver service that:

1. Implements the `SyncService` defined in `sync_service.proto`
2. Receives the gRPC calls from the controller
3. Handles the MongoDB operations

### Ready-to-Use Receiver Service

A complete gRPC receiver service implementation is available in the `grpc-receiver/` directory. This directory contains everything needed to run the receiver service and can be moved to a separate repository.

The receiver service includes:
- Complete Python implementation (`grpc_receiver_service.py`)
- Docker support with `Dockerfile` and `docker-compose.yml`
- Environment configuration (`.env.example`)
- Comprehensive documentation (`README.md`)
- gRPC code generation script (`generate_grpc.sh`)

To use the receiver service:

```bash
# Copy the receiver to your separate repository
cp -r grpc-receiver/ /path/to/your/receiver-repo/

# Follow the setup instructions in grpc-receiver/README.md
cd /path/to/your/receiver-repo/grpc-receiver/
```

## Deployment

The Docker image now automatically generates the gRPC code during build and uses the new gRPC-based controller.

Make sure your deployment includes the new environment variables for the gRPC server connection.
