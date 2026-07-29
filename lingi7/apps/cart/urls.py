from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("add/", views.CartAddView.as_view(), name="cart-add"),
    path("remove/", views.CartRemoveView.as_view(), name="cart-remove"),
    path("update-quantity/", views.CartUpdateQuantityView.as_view(), name="cart-update-quantity"),
]
