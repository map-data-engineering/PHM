from django.conf import settings
from django.db import models

from geo.models import District, Region, Ward


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    source = models.CharField(max_length=255, help_text="Source file label, e.g. the .xls filename")
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)

    row_count = models.PositiveIntegerField(default=0)
    geocoded_count = models.PositiveIntegerField(default=0)
    region_matched_count = models.PositiveIntegerField(default=0)
    district_matched_count = models.PositiveIntegerField(default=0)
    ward_matched_count = models.PositiveIntegerField(default=0)

    warnings = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.source} ({self.started_at:%Y-%m-%d %H:%M})"


class Outlet(models.Model):
    addo_uid = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    business_type = models.CharField(max_length=255, blank=True)
    accreditation_source = models.CharField(max_length=100, blank=True)
    po_box = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=100, blank=True)
    training_center = models.CharField(max_length=255, blank=True)
    village_street = models.CharField(max_length=255, blank=True)

    # As-submitted strings — kept even when the FK join below fails, for audit/display.
    region_name = models.CharField(max_length=200, blank=True)
    district_name = models.CharField(max_length=200, blank=True)
    ward_name = models.CharField(max_length=200, blank=True)
    region_raw_clean = models.CharField(max_length=200, blank=True)

    # Populated only on a successful point-in-polygon / fuzzy-name join.
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name="outlets")
    district = models.ForeignKey(District, on_delete=models.SET_NULL, null=True, blank=True, related_name="outlets")
    ward = models.ForeignKey(Ward, on_delete=models.SET_NULL, null=True, blank=True, related_name="outlets")

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    altitude = models.FloatField(null=True, blank=True)
    gps_source = models.CharField(max_length=100, blank=True)
    gps_accuracy = models.FloatField(null=True, blank=True)
    has_coords = models.BooleanField(default=False, db_index=True)

    import_batch = models.ForeignKey(
        ImportBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="outlets"
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["region", "district", "ward"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.addo_uid})"


class EditProposal(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    outlet = models.ForeignKey(Outlet, on_delete=models.CASCADE, related_name="edit_proposals")
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="proposed_edits"
    )
    changes = models.JSONField(help_text="Changeset: {field: new_value, ...}")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_edits",
    )
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Edit on {self.outlet.addo_uid} ({self.status})"
