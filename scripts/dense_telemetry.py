"""Explicit no-op product telemetry for the isolated Chroma 0.5.16 index."""
from chromadb.telemetry.product import ProductTelemetryClient, ProductTelemetryEvent


class DisabledTelemetry(ProductTelemetryClient):
    def capture(self, event: ProductTelemetryEvent) -> None:
        # Do not invoke PostHog or create its per-user identifier. This is
        # supplied through supported client settings, not a package patch.
        return None
