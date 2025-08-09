from rest_framework import generics

from django_stubs_ext import monkeypatch

monkeypatch(extra_classes=[generics.GenericAPIView])
