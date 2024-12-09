import discord
import asyncio
import logging
from database.manager import DatabaseManager
from config.settings import DB_URL
from collections import defaultdict
import pytz
from datetime import datetime
from typing import Dict, Optional

# Initialize global instances
db_manager = DatabaseManager(DB_URL)
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')

class ImageStore:
    def __init__(self):
        self._images: Dict[int, discord.Attachment] = {}
        self._lock = asyncio.Lock()
    
    async def set_image(self, user_id: int, image: discord.Attachment):
        async with self._lock:
            self._images[user_id] = image
    
    async def get_image(self, user_id: int) -> Optional[discord.Attachment]:
        async with self._lock:
            return self._images.get(user_id)
    
    async def clear_image(self, user_id: int):
        async with self._lock:
            self._images.pop(user_id, None)

# Change from private instance to public export
image_store = ImageStore()

class PaymentView(discord.ui.View):
    def __init__(self, user: discord.Member, channel: discord.TextChannel, 
        admin: discord.Member, transaction_id: int):
        super().__init__(timeout=None)
        self.user = user
        self.channel = channel
        self.admin = admin
        self.transaction_id = transaction_id
        self._lock = asyncio.Lock()

    @discord.ui.button(label="Submit Payment Proof", style=discord.ButtonStyle.primary)
    async def submit_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("You can't submit payment for another user!", ephemeral=True)
                return

            async with self._lock:
                image = await image_store.get_image(self.user.id)
                if not image:
                    await interaction.response.send_message(
                        "Please upload an image first, then click the submit button.", 
                        ephemeral=True
                    )
                    return

                await interaction.response.send_message("Processing your payment submission...", ephemeral=True)

                # Update transaction with image URL
                db_manager.update_transaction(self.transaction_id, image.url)

                # Cleanup old messages
                async for message in self.channel.history(limit=100):
                    if message.author == interaction.client.user:
                        if "Payment proof submitted" in message.content:
                            try:
                                await message.delete()
                            except discord.NotFound:
                                pass

                # Send new notification
                await self.channel.send(
                    f"Payment proof submitted by {self.user.mention}\n"
                    f"Admin {self.admin.mention} please verify."
                )

                # Update button state
                button.disabled = True
                await interaction.message.edit(view=self)

                # Clear stored image
                await image_store.clear_image(self.user.id)

        except Exception as e:
            logging.exception("Error in submit_payment")
            await interaction.followup.send(
                "An error occurred while processing your payment proof. Please try again.", 
                ephemeral=True
            )

    @discord.ui.button(label="Verify Payment", style=discord.ButtonStyle.green)
    async def verify_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.admin.id:
                await interaction.response.send_message("Only the admin can verify payments!", ephemeral=True)
                return

            async with self._lock:
                # Mark transaction as confirmed
                db_manager.confirm_transaction(self.transaction_id)

                # Update button state
                button.disabled = True
                await interaction.message.edit(view=self)

                # Get current time in Vietnam timezone
                current_date = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M (GMT+7)")
                
                await self.channel.send(
                    f"✅ Payment for {self.user.mention} verified by {self.admin.mention} on {current_date}"
                )

                await interaction.response.send_message("Payment verified successfully!", ephemeral=True)

        except Exception as e:
            logging.exception("Error in verify_payment")
            await interaction.response.send_message(
                "An error occurred while verifying the payment. Please try again.", 
                ephemeral=True
            )

    def stop(self):
        """Clean up view resources"""
        for item in self.children:
            item.disabled = True
        return super().stop()