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
        # Set custom_id for the whole view
        self.id = f"payment_view_{transaction_id}"

    # Add classmethod to recreate view
    @classmethod
    def create_from_custom_id(cls, custom_id: str, user: discord.Member, 
                            channel: discord.TextChannel, admin: discord.Member):
        transaction_id = int(custom_id.split('_')[-1])
        return cls(user, channel, admin, transaction_id)

    @discord.ui.button(
        label="Submit Payment Proof", 
        style=discord.ButtonStyle.primary,
        custom_id="submit_payment"
    )
    async def submit_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Add error logging
        logging.info(f"Submit payment interaction received for transaction {self.transaction_id}")

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
            logging.exception(f"Error in submit_payment for transaction {self.transaction_id}")
            await interaction.followup.send(
                "An error occurred while processing your payment proof. Please try again.", 
                ephemeral=True
            )

    @discord.ui.button(
        label="Verify Payment", 
        style=discord.ButtonStyle.green,
        custom_id="verify_payment"
    )
    async def verify_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        logging.info(f"Verify payment interaction received for transaction {self.transaction_id}")

        try:
            # Check if user has admin permissions
            member_perms = interaction.channel.permissions_for(interaction.user)
            if not (member_perms.administrator or member_perms.manage_messages):
                await interaction.response.send_message("Only administrators can verify payments!", ephemeral=True)
                return

            async with self._lock:
                # Mark all unpaid transactions as confirmed for this user
                db_manager.confirm_all_user_transactions(self.user.id)

                # Keep track of the payment image URL
                image_url = None
                async for message in self.channel.history(limit=100):
                    if message.author == interaction.client.user:
                        # If message has attachments, save the URL before deleting
                        if message.attachments:
                            image_url = message.attachments[0].url
                        # Delete all bot messages
                        try:
                            await message.delete()
                        except discord.NotFound:
                            continue

                # Get current time in Vietnam timezone
                current_date = datetime.now(vietnam_tz).strftime("%Y-%m-%d %H:%M (GMT+7)")
                
                # Send verification message with image if it exists
                verification_content = f"✅ All payments for {self.user.mention} verified by {interaction.user.mention} on {current_date}"
                if image_url:
                    embed = discord.Embed()
                    embed.set_image(url=image_url)
                    await self.channel.send(content=verification_content, embed=embed)
                else:
                    await self.channel.send(content=verification_content)

                await interaction.response.send_message("All payments verified successfully!", ephemeral=True)

        except Exception as e:
            logging.exception(f"Error in verify_payment for transaction {self.transaction_id}")
            await interaction.response.send_message(
                "An error occurred while verifying the payment. Please try again.", 
                ephemeral=True
            )

    def stop(self):
        """Clean up view resources"""
        for item in self.children:
            item.disabled = True
        return super().stop()