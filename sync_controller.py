import os
import logging
import json
from datetime import datetime
from kubernetes import client, config, watch
import grpc
import sentry_sdk
from dotenv import load_dotenv

# Import generated gRPC classes (will be generated after running generate_grpc.sh)
try:
    import sync_service_pb2
    import sync_service_pb2_grpc
except ImportError:
    print("gRPC classes not found. Please run: ./generate_grpc.sh")
    exit(1)

# Load environment variables from .env file
load_dotenv()


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

sentry_dsn = os.environ.get("DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
    )

# Get configuration from environment variables
GRPC_SERVER_HOST = os.environ.get("GRPC_SERVER_HOST", "localhost")
GRPC_SERVER_PORT = os.environ.get("GRPC_SERVER_PORT", "50051")
CLUSTER_CONFIG = os.environ.get("CLUSTER")


def get_cluster_name(logger):
    if CLUSTER_CONFIG:
        logger.info(f"Using cluster name from environment: {CLUSTER_CONFIG}")
        return CLUSTER_CONFIG
    try:
        v1 = client.CoreV1Api()
        nodes = v1.list_node()
        for node in nodes.items:
            for key in [
                "cluster-name",
                "kubernetes.azure.com/cluster",
                "eks.amazonaws.com/cluster-name",
            ]:
                if key in node.metadata.labels:
                    logger.info(
                        f"Detected cluster name from node label: {node.metadata.labels[key]}"
                    )
                    return node.metadata.labels[key]
    except Exception as e:
        logger.debug(f"Could not get cluster name from node labels: {e}")

    try:
        _, active_context = config.list_kube_config_contexts()
        if (
            active_context
            and "context" in active_context
            and "cluster" in active_context["context"]
        ):
            logger.info(
                f"Detected cluster name from kubeconfig: {active_context['context']['cluster']}"
            )
            return active_context["context"]["cluster"]
    except Exception as e:
        logger.debug(f"Could not get cluster name from kubeconfig: {e}")

    logger.info(
        f"Using cluster name from environment variable or default: {CLUSTER_CONFIG or 'unknown-cluster'}"
    )
    return CLUSTER_CONFIG or "unknown-cluster"


LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("sync-controller")
CLUSTER = get_cluster_name(logger)

# Create gRPC channel and stub
def create_grpc_client():
    channel = grpc.insecure_channel(f'{GRPC_SERVER_HOST}:{GRPC_SERVER_PORT}')
    stub = sync_service_pb2_grpc.SyncServiceStub(channel)
    return channel, stub

# Global gRPC client
grpc_channel, grpc_stub = create_grpc_client()


def load_kube_config():
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster kube config")
    except config.ConfigException:
        config.load_kube_config()
        logger.info("Loaded local kube config")


load_kube_config()

aqua_resources = [
    "vulnerabilityreports",
    "clustercompliancereports",
    "clusterconfigauditreports",
    "clusterinfraassessmentreports",
    "clusterrbacassessmentreports",
    "clustersbomreports",
    "clustervulnerabilityreports",
    "configauditreports",
    "exposedsecretreports",
    "infraassessmentreports",
    "rbacassessmentreports",
    "sbomreports",
]


def sync_to_grpc(resource_type, obj, event_type):
    """Send resource data to gRPC receiver instead of MongoDB"""
    meta = obj.get("metadata", {})
    uid = meta.get("uid")
    if not uid:
        logger.warning(f"No UID for {resource_type} {meta.get('name')}")
        return

    try:
        # Create gRPC request
        request = sync_service_pb2.SyncResourceRequest(
            event_type=event_type,
            resource_type=resource_type,
            namespace=meta.get("namespace", ""),
            name=meta.get("name", ""),
            cluster=CLUSTER,
            uid=uid,
            data_json=json.dumps(obj, cls=KubernetesJSONEncoder)
        )
        
        # Send to gRPC receiver
        response = grpc_stub.SyncResource(request)
        
        if response.success:
            logger.info(f"Synced {resource_type} {meta.get('name')} ({event_type}) via gRPC")
        else:
            logger.error(f"Failed to sync {resource_type} {meta.get('name')}: {response.message}")
            
    except grpc.RpcError as e:
        logger.error(f"gRPC error syncing {resource_type} {meta.get('name')}: {e}")
    except Exception as e:
        logger.error(f"Error syncing {resource_type} {meta.get('name')}: {e}")


def initial_import_resource(resource_type):
    group = "aquasecurity.github.io"
    version = "v1alpha1"
    plural = resource_type
    api = client.CustomObjectsApi()
    try:
        objs = api.list_cluster_custom_object(group, version, plural)
        items = objs.get("items", [])
        logger.info(f"Initial import: {len(items)} {resource_type}")
        for obj in items:
            sync_to_grpc(resource_type, obj, "INITIAL_IMPORT")
    except Exception as e:
        logger.error(f"Error during initial import of {resource_type}: {e}")


def watch_resource(resource_type):
    group = "aquasecurity.github.io"
    version = "v1alpha1"
    plural = resource_type
    api = client.CustomObjectsApi()
    w = watch.Watch()
    while True:
        try:
            for event in w.stream(
                api.list_cluster_custom_object,
                group,
                version,
                plural,
                timeout_seconds=60,
            ):
                obj = event["object"]
                event_type = event["type"]
                sync_to_grpc(resource_type, obj, event_type)
        except Exception as e:
            logger.error(f"Error watching {resource_type}: {e}")


def sync_namespace_to_grpc(obj, event_type):
    """Send namespace data to gRPC receiver instead of MongoDB"""
    meta = obj.get("metadata", {})
    uid = meta.get("uid")
    if not uid:
        logger.warning(f"No UID for namespace {meta.get('name')}")
        return

    try:
        # Create gRPC request
        request = sync_service_pb2.SyncNamespaceRequest(
            event_type=event_type,
            name=meta.get("name", ""),
            cluster=CLUSTER,
            uid=uid,
            data_json=json.dumps(obj, cls=KubernetesJSONEncoder)
        )
        
        # Send to gRPC receiver
        response = grpc_stub.SyncNamespace(request)
        
        if response.success:
            logger.info(f"Synced namespace {meta.get('name')} ({event_type}) via gRPC")
        else:
            logger.error(f"Failed to sync namespace {meta.get('name')}: {response.message}")
            
    except grpc.RpcError as e:
        logger.error(f"gRPC error syncing namespace {meta.get('name')}: {e}")
    except Exception as e:
        logger.error(f"Error syncing namespace {meta.get('name')}: {e}")


def initial_import_namespaces():
    v1 = client.CoreV1Api()
    try:
        ns_list = v1.list_namespace()
        logger.info(f"Initial import: {len(ns_list.items)} namespaces")
        for ns in ns_list.items:
            ns_dict = ns.to_dict()
            sync_namespace_to_grpc(ns_dict, "INITIAL_IMPORT")
    except Exception as e:
        logger.error(f"Error during initial import of namespaces: {e}")


def watch_namespaces():
    v1 = client.CoreV1Api()
    w = watch.Watch()
    while True:
        try:
            for event in w.stream(v1.list_namespace, timeout_seconds=60):
                obj = event["object"].to_dict()
                event_type = event["type"]
                sync_namespace_to_grpc(obj, event_type)
        except Exception as e:
            logger.error(f"Error watching namespaces: {e}")


if __name__ == "__main__":
    import threading

    # Test gRPC connection
    try:
        grpc.channel_ready_future(grpc_channel).result(timeout=10)
        logger.info(f"Connected to gRPC server at {GRPC_SERVER_HOST}:{GRPC_SERVER_PORT}")
    except grpc.FutureTimeoutError:
        logger.error(f"Failed to connect to gRPC server at {GRPC_SERVER_HOST}:{GRPC_SERVER_PORT}")
        exit(1)

    for res in aqua_resources:
        initial_import_resource(res)

    initial_import_namespaces()

    threads = []
    
    t_ns = threading.Thread(target=watch_namespaces, daemon=True)
    t_ns.start()
    threads.append(t_ns)
        
    for res in aqua_resources:
        t = threading.Thread(target=watch_resource, args=(res,), daemon=True)
        t.start()
        threads.append(t)
  

    
    logger.info("Controller started. Watching resources and namespaces...")
    for t in threads:
        t.join()
