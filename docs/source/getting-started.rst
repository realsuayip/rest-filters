Getting started
===============

In this following mini-tutorial, we will learn how to make use of some
``rest-filters`` features.

To begin, we need a model on which to construct QuerySet objects. Since the
User model is a common component in most applications, it will serve as the
example throughout this guide. Assume the following User model:

.. code-block:: python

    class Company(models.Model):
        name = models.CharField(max_length=100)
        address = models.CharField(max_length=100)

        created = models.DateTimeField(auto_now_add=True)


    class User(models.Model):
        username = models.CharField(max_length=50)

        first_name = models.CharField(max_length=50)
        last_name = models.CharField(max_length=50)

        company = models.ForeignKey(
            Company,
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
        )
        following_companies = models.ManyToManyField(Company)

        created = models.DateTimeField(auto_now_add=True)
