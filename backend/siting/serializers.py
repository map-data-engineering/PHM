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
