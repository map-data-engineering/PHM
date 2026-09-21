from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsDataTeam, IsRegulatorOrAbove
from geo.models import District, Region, Ward

from .filters import OutletFilter
from .models import EditProposal, Outlet
from .pagination import OutletPagination
from .serializers import (
    EditProposalCreateSerializer,
    EditProposalSerializer,
    OutletDetailSerializer,
    OutletListSerializer,
    OutletPointSerializer,
)


def _apply_changes(outlet, changes):
    for field, value in changes.items():
        setattr(outlet, field, value)
    outlet.save(update_fields=list(changes.keys()))


def _is_data_team(user):
    return user.is_superuser or user.groups.filter(name="Data Team").exists()


class OutletViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Outlet.objects.select_related("region", "district", "ward")
    filterset_class = OutletFilter
    pagination_class = OutletPagination
    lookup_field = "addo_uid"
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        return OutletDetailSerializer if self.action == "retrieve" else OutletListSerializer

    @action(detail=False, methods=["get"], pagination_class=None)
    def points(self, request):
        """Lightweight lat/lon dump for the always-on map layer — not the
        full record, and still respects the active filters, so it isn't a
        backdoor around the paginated /outlets/ endpoint's row cap."""
        qs = OutletFilter(request.GET, queryset=self.get_queryset().filter(has_coords=True)).qs
        return Response(OutletPointSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[IsRegulatorOrAbove], url_path="propose-edit")
    def propose_edit(self, request, addo_uid=None):
        outlet = self.get_object()
        serializer = EditProposalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changes = serializer.validated_data["changes"]

        data_team = _is_data_team(request.user)
        proposal = EditProposal.objects.create(
            outlet=outlet,
            proposed_by=request.user,
            changes=changes,
            status=EditProposal.Status.APPROVED if data_team else EditProposal.Status.PENDING,
            reviewed_by=request.user if data_team else None,
            reviewed_at=timezone.now() if data_team else None,
        )
        if data_team:
            _apply_changes(outlet, changes)

        return Response(EditProposalSerializer(proposal).data, status=status.HTTP_201_CREATED)


class EditProposalViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = EditProposal.objects.select_related("outlet", "proposed_by", "reviewed_by")
    serializer_class = EditProposalSerializer
    permission_classes = [IsRegulatorOrAbove]

    @action(detail=True, methods=["post"], permission_classes=[IsDataTeam])
    def approve(self, request, pk=None):
        proposal = self.get_object()
        _apply_changes(proposal.outlet, proposal.changes)
        proposal.status = EditProposal.Status.APPROVED
        proposal.reviewed_by = request.user
        proposal.reviewed_at = timezone.now()
        proposal.review_note = request.data.get("note", "")
        proposal.save()
        return Response(EditProposalSerializer(proposal).data)

    @action(detail=True, methods=["post"], permission_classes=[IsDataTeam])
    def reject(self, request, pk=None):
        proposal = self.get_object()
        proposal.status = EditProposal.Status.REJECTED
        proposal.reviewed_by = request.user
        proposal.reviewed_at = timezone.now()
        proposal.review_note = request.data.get("note", "")
        proposal.save()
        return Response(EditProposalSerializer(proposal).data)


def registry_page(request):
    return render(request, "outlets/registry.html")


LEVEL_MODELS = {"region": Region, "district": District, "ward": Ward}
LEVEL_FK = {"region": "region", "district": "district", "ward": "ward"}


class BoundaryView(APIView):
    """FeatureCollection for one admin level, with addo_count annotated live
    from the same filters the Registry's outlet list uses — replaces the old
    static site's baked-in-at-build-time counts."""

    permission_classes = [AllowAny]

    def get(self, request, level):
        model = LEVEL_MODELS.get(level)
        if model is None:
            return Response({"detail": "level must be one of region, district, ward"}, status=400)

        if level == "region":
            features_qs = model.objects.all()
        elif level == "district":
            region_name = request.GET.get("region")
            features_qs = model.objects.filter(region__name__iexact=region_name) if region_name else model.objects.all()
        else:
            district_name = request.GET.get("district")
            features_qs = model.objects.filter(district__name__iexact=district_name) if district_name else model.objects.all()

        outlet_filters = {}
        if request.GET.get("business_type"):
            outlet_filters["business_type__iexact"] = request.GET["business_type"]
        if request.GET.get("accreditation_source"):
            outlet_filters["accreditation_source__iexact"] = request.GET["accreditation_source"]
        if request.GET.get("search"):
            outlet_filters["name__icontains"] = request.GET["search"]

        fk_name = LEVEL_FK[level]
        counts = dict(
            Outlet.objects.filter(**{f"{fk_name}__in": features_qs}, **outlet_filters)
            .values_list(fk_name)
            .annotate(n=Count("id"))
        )

        features = [
            {
                "type": "Feature",
                "geometry": obj.geometry,
                "properties": {"gid": obj.gid, "name": obj.name, "addo_count": counts.get(obj.id, 0)},
            }
            for obj in features_qs
        ]
        return Response({"type": "FeatureCollection", "features": features})
