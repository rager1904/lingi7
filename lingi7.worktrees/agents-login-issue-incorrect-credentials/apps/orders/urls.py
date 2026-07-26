from django.urls import path
from apps.orders import views

app_name = "orders"

urlpatterns = [
    # Order CRUD
    path("", views.OrderListCreateView.as_view(), name="order-list-create"),
    path("<uuid:pk>/", views.OrderDetailView.as_view(), name="order-detail"),

    # State transitions
    path("<uuid:pk>/submit/", views.OrderSubmitView.as_view(), name="order-submit"),
    path("<uuid:pk>/acknowledge/", views.OrderAcknowledgeView.as_view(), name="order-acknowledge"),
    path("<uuid:pk>/ship/", views.OrderShipView.as_view(), name="order-ship"),
    path("<uuid:pk>/confirm-delivery/", views.OrderConfirmDeliveryView.as_view(), name="order-confirm-delivery"),
    path("<uuid:pk>/complete/", views.OrderCompleteView.as_view(), name="order-complete"),
    path("<uuid:pk>/cancel/", views.OrderCancelView.as_view(), name="order-cancel"),

    # Disputes
    path("<uuid:pk>/dispute/", views.OrderDisputeView.as_view(), name="order-dispute"),
    path("disputes/<uuid:dispute_pk>/resolve/", views.DisputeResolveView.as_view(), name="dispute-resolve"),
]
