import json
from channels.generic.websocket import AsyncWebsocketConsumer

class CampaignProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.campaign_id = self.scope["url_route"]["kwargs"]["campaign_id"]
        self.group_name = f"campaign_{self.campaign_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def campaign_progress(self, event):
        await self.send(text_data=json.dumps(event["message"]))
