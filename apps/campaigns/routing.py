from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/campaigns/(?P<campaign_id>[0-9a-f-]+)/$", consumers.CampaignProgressConsumer.as_asgi()),
]
