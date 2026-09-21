from django.db import models


class Region(models.Model):
    gid = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=200)
    geometry = models.JSONField(help_text="GeoJSON geometry for this region's boundary")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class District(models.Model):
    gid = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=200)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="districts")
    geometry = models.JSONField(help_text="GeoJSON geometry for this district's boundary")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ward(models.Model):
    gid = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=200)
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="wards")
    geometry = models.JSONField(help_text="GeoJSON geometry for this ward's boundary")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
