from django.contrib import admin

from .models import District, Region, Ward


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "gid")
    search_fields = ("name", "gid")


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "gid")
    list_filter = ("region",)
    search_fields = ("name", "gid")


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "gid")
    list_filter = ("district__region", "district")
    search_fields = ("name", "gid")
