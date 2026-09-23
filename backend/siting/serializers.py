from rest_framework import serializers

MODES = ["driving-car", "cycling-regular", "foot-walking"]


class NearestOutletsRequestSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    business_type = serializers.CharField(required=False, allow_blank=True, default="")
    mode = serializers.ChoiceField(choices=MODES, default="driving-car")
    count = serializers.IntegerField(min_value=1, max_value=20, default=5)


class SiteCheckRequestSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    radius_km = serializers.FloatField(min_value=0.5, max_value=10, default=2.0)
    mode = serializers.ChoiceField(choices=MODES, default="driving-car")

    # What's being sited — section 1.2.3 exempts wholesale/warehouse
    # applications from the pharmacy-distance rule entirely.
    application_type = serializers.ChoiceField(
        choices=["retail_pharmacy", "wholesale"], default="retail_pharmacy"
    )
    # Section 1.2.1/1.2.2 — relaxes the distance rule to 100m in high-population
    # / market / bus-stand areas, at the Council's discretion.
    high_population_area = serializers.BooleanField(default=False)

    # Self-declared exemptions (sections 1.6-1.10) — facts about this specific
    # premises that a GPS check alone can't infer, so the regulator confirms
    # them explicitly before the distance rule is bypassed.
    is_addo_upgrade = serializers.BooleanField(default=False)
    is_previously_registered_pharmacy = serializers.BooleanField(default=False)
    is_double_tarmac_separated = serializers.BooleanField(default=False)
    is_force_majeure_relocation = serializers.BooleanField(default=False)
    is_building_complex = serializers.BooleanField(default=False)
