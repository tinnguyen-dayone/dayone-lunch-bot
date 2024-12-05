import discord
import asyncio
import logging
from database.manager import DatabaseManager
from config.settings import DB_URL
from collections import defaultdict

db_manager = DatabaseManager(DB_URL)

# Dictionary to track users' last uploaded image
user_last_image = defaultdict(lambda: None)

class PaymentView(discord.ui.View):
    def __init__(self, user, channel, admin, transaction_id):
        super().__init__()
        self.user = user
        self.channel = channel
        self.admin = admin
        self.transaction_id = transaction_id

    @discord.ui.button(label="Submit Payment Proof", style=discord.ButtonStyle.primary)
    async def submit_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("You can't submit payment for another user!", ephemeral=True)
                return

            image = user_last_image.get(self.user.id)
            if not image:
                await interaction.response.send_message("Please upload an image first, then click the submit button.", ephemeral=True)
                return

            image_url = image.url
            db_manager.update_transaction(self.transaction_id, image_url)
            
            await interaction.response.send_message("Processing your payment submission...", ephemeral=True)
            
            await self.channel.send(
                content=f"Payment proof submitted by {self.user.mention}\nAdmin {self.admin.mention} please verify.",
                file=await image.to_file()
            )
            button.disabled = True
            await interaction.message.edit(view=self)
            user_last_image[self.user.id] = None  # Reset after submission
        except Exception as e:
            logging.exception("Error in submit_payment")  # Changed from logging.error(...)
            await interaction.response.send_message("An error occurred while processing your payment proof. Please try again.", ephemeral=True)

    @discord.ui.button(label="Verify Payment", style=discord.ButtonStyle.green)
    async def verify_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.admin.id:
                await interaction.response.send_message("Only the admin can verify payments!", ephemeral=True)
                return

            # Confirm the transaction in database first
            db_manager.confirm_transaction(self.transaction_id)
            
            
            # Delete all messages in the ticket channel that contain embeds
            async for message in self.channel.history():
                if message.embeds:
                    try:
                        await message.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass  # Skip if message is already deleted
                    except Exception as e:
                        logging.error(f"Error deleting message: {e}")

            # Reset all unpaid transactions for this user
            db_manager.reset_user_data(self.user.id)

            # Try to disable the button, but don't error if message is gone
            try:
                button.disabled = True
                await interaction.message.edit(view=self)
            except discord.NotFound:
                pass  # Message was already deleted, ignore
            except Exception as e:
                logging.error(f"Error updating button state: {e}")

            # Send a final confirmation message in the channel with date
            current_date = discord.utils.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            await self.channel.send(f"✅ All payments for {self.user.mention} have been verified by {self.admin.mention} on {current_date}.")

        except Exception as e:
            logging.exception("Error in verify_payment")
            await interaction.response.send_message("An error occurred while verifying the payment. Please try again.", ephemeral=True)