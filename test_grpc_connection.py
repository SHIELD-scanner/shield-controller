#!/usr/bin/env python3
"""Test script to verify gRPC connection to the receiver service."""

import json
import os
import sys
from datetime import datetime

import grpc

# Add the current directory to path so we can import generated proto files
sys.path.append('.')


class KubernetesJSONEncoder(json.JSONEncoder):

    """Custom JSON encoder to handle Kubernetes objects with datetime and other non-serializable types"""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Handle any other non-serializable objects by converting to string
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

try:
    import sync_service_pb2
    import sync_service_pb2_grpc
except ImportError:
    print("Error: gRPC classes not found. Please run: ./generate_grpc.sh")
    sys.exit(1)


def test_grpc_connection():
    """Test the gRPC connection and send a sample resource"""
    # Configuration
    grpc_host = os.environ.get("GRPC_SERVER_HOST", "localhost")
    grpc_port = os.environ.get("GRPC_SERVER_PORT", "50051")
    
    print(f"Testing connection to gRPC server at {grpc_host}:{grpc_port}")
    
    try:
        # Create gRPC channel
        channel = grpc.insecure_channel(f'{grpc_host}:{grpc_port}')
        stub = sync_service_pb2_grpc.SyncServiceStub(channel)
        
        # Test connection
        grpc.channel_ready_future(channel).result(timeout=10)
        print("✓ Connected to gRPC server")
        
        # Create a test resource
        test_resource = {
            "apiVersion": "aquasecurity.github.io/v1alpha1",
            "kind": "VulnerabilityReport",
            "metadata": {
                "name": "test-resource",
                "namespace": "default",
                "uid": "test-uid-12345"
            },
            "spec": {},
            "status": {}
        }
        
        # Create gRPC request
        request = sync_service_pb2.SyncResourceRequest(
            event_type="TEST",
            resource_type="vulnerabilityreports",
            namespace="default",
            name="test-resource",
            cluster="test-cluster",
            uid="test-uid-12345",
            data_json=json.dumps(test_resource, cls=KubernetesJSONEncoder)
        )
        
        # Send the request
        print("Sending test resource...")
        response = stub.SyncResource(request)
        
        if response.success:
            print("✓ Test resource sent successfully")
            print(f"  Response: {response.message}")
        else:
            print("✗ Failed to send test resource")
            print(f"  Error: {response.message}")
            return False
            
        # Test namespace sync
        test_namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": "test-namespace",
                "uid": "test-ns-uid-12345"
            }
        }
        
        namespace_request = sync_service_pb2.SyncNamespaceRequest(
            event_type="TEST",
            name="test-namespace",
            cluster="test-cluster",
            uid="test-ns-uid-12345",
            data_json=json.dumps(test_namespace, cls=KubernetesJSONEncoder)
        )
        
        print("Sending test namespace...")
        ns_response = stub.SyncNamespace(namespace_request)
        
        if ns_response.success:
            print("✓ Test namespace sent successfully")
            print(f"  Response: {ns_response.message}")
        else:
            print("✗ Failed to send test namespace")
            print(f"  Error: {ns_response.message}")
            return False
            
        print("\n✓ All tests passed! gRPC connection is working correctly.")
        return True
        
    except grpc.FutureTimeoutError:
        print(f"✗ Failed to connect to gRPC server at {grpc_host}:{grpc_port}")
        print("  Make sure the receiver service is running and accessible")
        return False
    except grpc.RpcError as e:
        print(f"✗ gRPC error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False
    finally:
        try:
            channel.close()
        except Exception:
            pass


if __name__ == "__main__":
    success = test_grpc_connection()
    sys.exit(0 if success else 1)
