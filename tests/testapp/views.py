from rest_framework import serializers
from rest_framework.generics import ListAPIView

from tests.testapp.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User


class UserView(ListAPIView[User]):
    serializer_class = UserSerializer
    queryset = User.objects.all()
