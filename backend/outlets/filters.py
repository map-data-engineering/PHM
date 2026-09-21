import django_filters

from .models import Outlet


class OutletFilter(django_filters.FilterSet):
    region = django_filters.CharFilter(field_name="region__name", lookup_expr="iexact")
    district = django_filters.CharFilter(field_name="district__name", lookup_expr="iexact")
    ward = django_filters.CharFilter(field_name="ward__name", lookup_expr="iexact")
    business_type = django_filters.CharFilter(field_name="business_type", lookup_expr="iexact")
    accreditation_source = django_filters.CharFilter(field_name="accreditation_source", lookup_expr="iexact")
    search = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        model = Outlet
        fields = ["region", "district", "ward", "business_type", "accreditation_source", "search"]
