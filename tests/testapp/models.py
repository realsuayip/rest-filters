from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class User(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)

    username = models.CharField(max_length=50)
    created = models.DateTimeField(auto_now_add=True)

    following_companies = models.ManyToManyField(Company)

    role = models.CharField(max_length=10)
    location = models.TextField()

    def __str__(self) -> str:
        return self.username
