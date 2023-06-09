from django.db import models

# Add Model Manager class here
class HolidayManager(models.Manager):
    def search_holidays(self, query):
        return self.filter(
            models.Q(name__icontains=query) |
            models.Q(date__icontains=query) |
            models.Q(country__icontains=query) |
            models.Q(description__icontains=query)
        )

    def is_holiday(self, date, country):
        return self.filter(date=date, country=country).exists()

class Holiday(models.Model):
    name = models.CharField(max_length=50)
    date = models.DateField()
    is_weekend = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    country = models.CharField(max_length=50)
    objects = HolidayManager()

    class Meta:
        ordering = ['date']
        indexes = [
            models.Index(fields=['country']),
            models.Index(fields=['date']),
            models.Index(fields=['is_weekend']),
        ]

        unique_together = (('date', 'country'),)

    def __str__(self):
        return self.name + ' - ' + self.date.strftime('%d %b %Y')

    def save(self, *args, **kwargs):
        self.is_weekend = self.date.weekday() in [5, 6]
        super().save(*args, **kwargs)


    @classmethod
    def get_holidays(cls, country):
        """
        Returns a list of holidays for the given country.
        """
        return cls.objects.filter(country=country)
