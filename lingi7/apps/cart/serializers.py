from rest_framework import serializers


class CartAddSerializer(serializers.Serializer):
    item = serializers.CharField()
    amount = serializers.IntegerField(min_value=1, default=1)
    price = serializers.FloatField(required=False, allow_null=True)



class CartRemoveSerializer(serializers.Serializer):
    item = serializers.CharField()
    amount = serializers.IntegerField(min_value=1, default=1)
