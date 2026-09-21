from django.contrib import admin

from .models import EditProposal, ImportBatch, Outlet


@admin.register(Outlet)
class OutletAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "addo_uid",
        "business_type",
        "accreditation_source",
        "region",
        "district",
        "ward",
        "has_coords",
    )
    list_filter = ("business_type", "accreditation_source", "has_coords", "region", "district")
    search_fields = ("name", "addo_uid", "region_name", "district_name", "ward_name")
    autocomplete_fields = ("region", "district", "ward")
    readonly_fields = ("import_batch",)


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "status",
        "started_at",
        "finished_at",
        "row_count",
        "geocoded_count",
        "region_matched_count",
        "district_matched_count",
        "ward_matched_count",
    )
    list_filter = ("status",)
    readonly_fields = [f.name for f in ImportBatch._meta.fields]


@admin.register(EditProposal)
class EditProposalAdmin(admin.ModelAdmin):
    list_display = ("outlet", "proposed_by", "status", "created_at", "reviewed_by", "reviewed_at")
    list_filter = ("status",)
    search_fields = ("outlet__name", "outlet__addo_uid")
    autocomplete_fields = ("outlet",)
