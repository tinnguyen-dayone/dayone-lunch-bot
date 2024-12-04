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
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("You can't submit payment for another user!", ephemeral=True)
            return

        image = user_last_image.get(self.user.id)
        if not image:
            await interaction.response.send_message("Please upload an image first, then click the submit button.", ephemeral=True)
            return

        try:
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
            logging.error(f"Error in submit_payment: {str(e)}")
            await interaction.response.send_message("An error occurred while processing your payment proof. Please try again.", ephemeral=True)

    @discord.ui.button(label="Verify Payment", style=discord.ButtonStyle.green)
    async def verify_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.admin.id:
            await interaction.response.send_message("Only the admin can verify payments!", ephemeral=True)
            return

        db_manager.confirm_transaction(self.transaction_id)
        
        # Calculate the new total unpaid and count
        user_id = self.user.id
        total_unpaid = db_manager.get_unpaid_total(user_id)
        unpaid_count = db_manager.get_unpaid_count(user_id)
        
        # Retrieve the user's current ticket message ID
        ticket_message_id = db_manager.get_user_ticket_message_id(user_id)
        
        if total_unpaid == 0.0:
            # All transactions are paid; delete the embed message
            try:
                ticket_message = await self.channel.fetch_message(ticket_message_id)
                await ticket_message.delete()
                logging.info(f"All payments completed. Deleted ticket message ID {ticket_message_id} for user {self.user.name}.")
                # Optionally, remove the ticket_message_id from the database
                db_manager.set_user_ticket_message_id(user_id, None)
            except discord.NotFound:
                logging.warning(f"Ticket message ID {ticket_message_id} not found for user {self.user.name}.")
            except discord.Forbidden:
                logging.error(f"Forbidden to delete ticket message ID {ticket_message_id} for user {self.user.name}.")
            except Exception as e:
                logging.error(f"Error deleting ticket message for user {self.user.name}: {e}")
        else:
            # Update the embed with the new total unpaid and count
            try:
                ticket_message = await self.channel.fetch_message(ticket_message_id)
                new_embed = discord.Embed(
                    title="🍽️ Lunch Ticket",
                    description="Your lunch ticket has been updated.",
                    color=discord.Color.green()
                )
                new_embed.add_field(name="Total Unpaid Lunch", value=f"{total_unpaid:.3f} VND", inline=True)
                new_embed.add_field(name="Unpaid Transactions", value=str(unpaid_count), inline=True)
                new_embed.add_field(
                    name="Instructions", 
                    value="1. Take a screenshot of your payment transaction\n2. Upload the payment screenshot and click 'Submit Payment Proof'\n3. Wait for admin verification",
                    inline=False
                )
                new_embed.set_footer(text="Please complete the payment within 24 hours")
                
                await ticket_message.edit(embed=new_embed)
                logging.info(f"Updated ticket message ID {ticket_message_id} for user {self.user.name} with new total unpaid {total_unpaid:.3f} VND and count {unpaid_count}.")
            except discord.NotFound:
                logging.warning(f"Ticket message ID {ticket_message_id} not found for user {self.user.name}.")
            except discord.Forbidden:
                logging.error(f"Forbidden to edit ticket message ID {ticket_message_id} for user {self.user.name}.")
            except Exception as e:
                logging.error(f"Error updating ticket message for user {self.user.name}: {e}")

        await interaction.response.send_message("Payment verified!", ephemeral=True)
        button.disabled = True
        await interaction.message.edit(view=self)