from django.urls import re_path

from .consumers import KitchenConsumer

websocket_urlpatterns = [
    re_path(r"^ws/kitchen/$", KitchenConsumer.as_asgi()),
]
