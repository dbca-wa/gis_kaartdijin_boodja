"""Views for the kb_geoserver_manager API.

Provides three endpoints consumed exclusively by the kb_geoserver_manager service:

    GET  /api/geoserver-manager/layers/?status=<int>   — list queue items by status
    GET  /api/geoserver-manager/layers/<pk>/download/  — stream the converted GIS file
    PATCH /api/geoserver-manager/layers/<pk>/          — update queue item status

Authentication: Token-based (DRF TokenAuthentication).
"""

# Standard
import logging
import pathlib

# Third-Party
from django.http import StreamingHttpResponse
from rest_framework import status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# Local
from govapp.apps.publisher.models.geoserver_queues import (
    GeoServerQueue,
    GeoServerQueueStatus,
    GeoServerQueueType,
)
from govapp.apps.publisher.serializers.geoserver_manager import (
    GeoServerManagerQueueSerializer,
    GeoServerManagerStatusUpdateSerializer,
)

log = logging.getLogger(__name__)

_CHUNK_SIZE = 8 * 1024  # 8 KB

# Valid preceding statuses for each transition allowed by kb_geoserver_manager
_VALID_PREDECESSORS = {
    GeoServerQueueStatus.UPLOAD_IN_PROGRESS: {GeoServerQueueStatus.CONVERTED},
    GeoServerQueueStatus.UPLOAD_FAILED: {GeoServerQueueStatus.UPLOAD_IN_PROGRESS},
    GeoServerQueueStatus.READY_TO_PUBLISH: {GeoServerQueueStatus.UPLOAD_IN_PROGRESS},
}


def _stream_file(file_path: pathlib.Path, chunk_size: int = _CHUNK_SIZE):
    """Generator that yields a file in fixed-size chunks without loading it into memory."""
    with file_path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            yield chunk


class GeoServerManagerQueueViewSet(viewsets.GenericViewSet):
    """ViewSet for kb_geoserver_manager to interact with GeoServerQueue items.

    Only PUBLISH-type queue items are exposed.
    """

    queryset = GeoServerQueue.objects.filter(
        queue_type=GeoServerQueueType.PUBLISH
    ).select_related("publish_entry").order_by("created_at")
    serializer_class = GeoServerManagerQueueSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """Return PUBLISH queue items, optionally filtered by ``?status=<int>``."""
        queryset = self.get_queryset()
        status_param = request.query_params.get("status")
        if status_param is not None:
            try:
                status_int = int(status_param)
            except ValueError:
                return Response(
                    {"detail": "status must be an integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=status_int)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def partial_update(self, request, pk=None):
        """Update the status of a queue item.

        Only the three transitions authorised for kb_geoserver_manager are accepted.
        The current status is validated to ensure the transition is legal.
        """
        queue_item = self.get_object()
        serializer = GeoServerManagerStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        valid_predecessors = _VALID_PREDECESSORS.get(new_status, set())
        if queue_item.status not in valid_predecessors:
            current_label = GeoServerQueueStatus(queue_item.status).name.lower()
            new_label = GeoServerQueueStatus(new_status).name.lower()
            return Response(
                {
                    "detail": (
                        f"Cannot transition from '{current_label}' to '{new_label}'. "
                        f"Expected current status: "
                        + ", ".join(
                            GeoServerQueueStatus(s).name.lower() for s in valid_predecessors
                        )
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        queue_item.change_status(new_status)
        log.info(
            f"GeoServerQueue pk={queue_item.pk} status changed to "
            f"{GeoServerQueueStatus(new_status).name} by kb_geoserver_manager "
            f"(user={request.user})."
        )
        return Response(GeoServerManagerQueueSerializer(queue_item).data)

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        """Stream the converted GIS file without loading it into memory.

        Uses Django's ``StreamingHttpResponse`` with a generator that reads
        the file in ``_CHUNK_SIZE`` chunks.
        """
        queue_item = self.get_object()

        if not queue_item.converted_file_path:
            return Response(
                {"detail": "No converted file is available for this queue item."},
                status=status.HTTP_404_NOT_FOUND,
            )

        file_path = pathlib.Path(queue_item.converted_file_path)
        if not file_path.exists():
            log.error(
                f"Converted file not found on disk for GeoServerQueue pk={queue_item.pk}: "
                f"{file_path}"
            )
            return Response(
                {"detail": "Converted file not found on disk."},
                status=status.HTTP_404_NOT_FOUND,
            )

        response = StreamingHttpResponse(
            streaming_content=_stream_file(file_path),
            content_type="application/octet-stream",
        )
        response["Content-Disposition"] = f'attachment; filename="{file_path.name}"'
        return response
