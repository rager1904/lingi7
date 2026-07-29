from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import CartAddSerializer
from .services import sync_cart_add


class CartAddView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CartAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = sync_cart_add(
            user_id=request.user.id,
            item=data["item"],
            amount=data["amount"],
            price=data.get("price"),
        )

        if "error" in result:
            return Response(result, status=status.HTTP_502_BAD_GATEWAY)

        return Response(result, status=status.HTTP_200_OK)



class CartRemoveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CartRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = sync_cart_remove(
            user_id=request.user.id,
            item=data["item"],
            amount=data["amount"],
        )

        if "error" in result:
            return Response(result, status=status.HTTP_502_BAD_GATEWAY)

        return Response(result, status=status.HTTP_200_OK)


class CartUpdateQuantityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CartAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = sync_cart_update(
            user_id=request.user.id,
            item=data["item"],
            amount=data["amount"],
            price=data.get("price"),
        )

        if "error" in result:
            return Response(result, status=status.HTTP_502_BAD_GATEWAY)

        return Response(result, status=status.HTTP_200_OK)
