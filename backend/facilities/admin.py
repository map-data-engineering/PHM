from django.contrib import admin

from .models import HealthFacility


@admin.register(HealthFacility)
class HealthFacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "tier", "ownership", "region_name", "district_name")
    list_filter = ("tier", "ownership", "region_name")
    search_fields = ("name", "region_name", "district_name")
