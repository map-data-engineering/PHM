from django.db import models


class HealthFacility(models.Model):
    """Public/private hospitals, health centres and dispensaries — used only
    to check Site Check's distance-from-health-facility rule (Pharmacy
    Council "Procedures for Approving Location of New Pharmacy Premises",
    section 1.3). Empty until a real dataset is imported; siting/services
    treats an empty table as "rule not evaluated", not "rule passed"."""

    class Tier(models.TextChoices):
        TERTIARY = "tertiary", "Tertiary (Zonal/National Referral Hospital)"
        REGIONAL = "regional", "Regional Referral Hospital"
        DISTRICT = "district", "District Hospital"
        HEALTH_CENTRE = "health_centre", "Health Centre"
        DISPENSARY = "dispensary", "Dispensary"
        LABORATORY = "laboratory", "Standalone Medical Laboratory"

    class Ownership(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"
        UNKNOWN = "unknown", "Unknown"

    name = models.CharField(max_length=255)
    facility_code = models.CharField(max_length=50, blank=True)
    tier = models.CharField(max_length=20, choices=Tier.choices)
    ownership = models.CharField(max_length=10, choices=Ownership.choices, default=Ownership.UNKNOWN)
    latitude = models.FloatField()
    longitude = models.FloatField()
    region_name = models.CharField(max_length=200, blank=True)
    district_name = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=255, blank=True, help_text="Where this record came from")

    class Meta:
        indexes = [models.Index(fields=["tier"]), models.Index(fields=["ownership"])]
        verbose_name_plural = "health facilities"

    def __str__(self):
        return f"{self.name} ({self.get_tier_display()})"
