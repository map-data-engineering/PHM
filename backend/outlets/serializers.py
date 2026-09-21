from rest_framework import serializers

from .models import EditProposal, Outlet

# Fields an EditProposal is allowed to touch. Reassigning region/district/ward
# goes through the boundary join (import_outlets), not this endpoint.
EDITABLE_FIELDS = [
    "name", "business_type", "accreditation_source", "po_box", "phone",
    "training_center", "village_street", "latitude", "longitude", "altitude",
]


class OutletListSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source="region.name", default="", read_only=True)
    district = serializers.CharField(source="district.name", default="", read_only=True)
    ward = serializers.CharField(source="ward.name", default="", read_only=True)

    class Meta:
        model = Outlet
        fields = [
            "addo_uid", "name", "business_type", "accreditation_source",
            "region", "district", "ward", "latitude", "longitude", "has_coords",
        ]


class OutletDetailSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source="region.name", default="", read_only=True)
    district = serializers.CharField(source="district.name", default="", read_only=True)
    ward = serializers.CharField(source="ward.name", default="", read_only=True)

    class Meta:
        model = Outlet
        fields = [
            "addo_uid", "name", "business_type", "accreditation_source",
            "po_box", "phone", "training_center", "village_street",
            "region", "district", "ward",
            "region_name", "district_name", "ward_name",
            "latitude", "longitude", "altitude", "gps_source", "gps_accuracy", "has_coords",
        ]


class OutletPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = Outlet
        fields = ["addo_uid", "name", "business_type", "latitude", "longitude"]


class EditProposalCreateSerializer(serializers.Serializer):
    changes = serializers.DictField()

    def validate_changes(self, value):
        if not value:
            raise serializers.ValidationError("changes cannot be empty")
        bad = set(value) - set(EDITABLE_FIELDS)
        if bad:
            raise serializers.ValidationError(f"Not editable: {', '.join(sorted(bad))}")
        return value


class EditProposalSerializer(serializers.ModelSerializer):
    outlet = serializers.CharField(source="outlet.addo_uid", read_only=True)
    proposed_by = serializers.CharField(source="proposed_by.username", default="", read_only=True)
    reviewed_by = serializers.CharField(source="reviewed_by.username", default="", read_only=True)

    class Meta:
        model = EditProposal
        fields = [
            "id", "outlet", "proposed_by", "changes", "status",
            "reviewed_by", "review_note", "created_at", "reviewed_at",
        ]
        read_only_fields = fields
