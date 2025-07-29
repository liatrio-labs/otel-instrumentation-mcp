load('ext://git_resource', 'git_checkout')

# Clone the external repository
git_checkout('git@github.com:liatrio/tag-o11y-quick-start-manifests.git', 'quickstarts')

# Load the Tiltfile from the cloned repository
include('quickstarts/apps/Tiltfile')

# Build configuration with optimized live updates
docker_build('otel-basic-registry:55166/otel-instrumentation-mcp', '.')

k8s_yaml(kustomize("./manifests/overlays/local/"))

k8s_resource(
  workload="otel-instrumentation-mcp",
  port_forwards=8080,
  labels=[
    "otel-instrumentation-mcp"
  ]
)

k8s_resource(
  new_name="otelcol-collector",
  objects=[
    "otelcol:OpenTelemetryCollector:otel-instrumentation-mcp",
  ],
  labels=[
    "otel-instrumentation-mcp"
  ],
  resource_deps=[
    "opentelemetry-operator-controller-manager"
  ]
)
