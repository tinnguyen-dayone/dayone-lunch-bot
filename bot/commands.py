from discord.ext import commands
import discord  # Added import
import logging
from database.manager import DatabaseManager
from config.settings import DB_URL, LUNCH_PRICE
from utils.helpers import create_ticket_channel, create_lunch_ticket_embed
from bot.views import PaymentView
from datetime import datetime

db_manager = DatabaseManager(DB_URL)

def setup_commands(bot):
    @bot.command(name='setprice')
    async def set_lunch_price(ctx, price: str):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("Only administrators can set lunch prices!")
            return
        
        global LUNCH_PRICE
        LUNCH_PRICE = price
        await ctx.send(f"Lunch price updated to: {price}")

    @bot.command(name='comment')
    async def comment(ctx, price: str, *users: discord.Member):
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("You don't have permission to use this command.")
            return
        
        if not users:
            await ctx.send("Please mention at least one user!")
            return

        for user in users:
            logging.info(f'Admin commenting {user.name} with price {price} in {ctx.guild.name}')
            
            # Sanitize and convert price to numeric
            numeric_price = ''.join(filter(lambda x: x.isdigit() or x == '.', price))
            try:
                numeric_price = float(numeric_price)
            except ValueError:
                logging.error(f"Invalid price format: {price}")
                await ctx.send(f"Invalid price format for user {user.mention}. Please use a numeric value like '55.000 VND'.")
                continue
            
            # Create a new transaction
            transaction_id = db_manager.increment_commentation_with_price(user.id, price)
            
            # Calculate total unpaid and count
            total_unpaid = db_manager.get_unpaid_total(user.id)
            unpaid_count = db_manager.get_unpaid_count(user.id)
            
            # Retrieve the old ticket message ID
            old_ticket_message_id = db_manager.get_user_ticket_message_id(user.id)
            ticket_channel = await create_ticket_channel(ctx.guild, ctx.author, user)
            
            # Delete the old embed message if it exists
            if old_ticket_message_id:
                try:
                    old_message = await ticket_channel.fetch_message(old_ticket_message_id)
                    await old_message.delete()
                    logging.info(f"Deleted old ticket message ID {old_ticket_message_id} for user {user.name}.")
                except discord.NotFound:
                    logging.warning(f"Old ticket message ID {old_ticket_message_id} not found for user {user.name}.")
                except discord.Forbidden:
                    logging.error(f"Forbidden to delete message ID {old_ticket_message_id} for user {user.name}.")
                except Exception as e:
                    logging.error(f"Error deleting old ticket message for user {user.name}: {e}")
            
            # Create new embed with updated total and count
            embed = create_lunch_ticket_embed(
                user, 
                price, 
                total_unpaid, 
                unpaid_count, 
                current_date=datetime.now().strftime("%Y-%m-%d")
            )
            
            try:
                sent_message = await ticket_channel.send(
                    embed=embed,
                    view=PaymentView(user, ticket_channel, ctx.author, transaction_id)
                )
                # Store the new message ID in the database
                db_manager.set_user_ticket_message_id(user.id, sent_message.id)
                logging.info(f"Ticket created for user {user.name} with transaction ID {transaction_id} and message ID {sent_message.id}.")
            except discord.Forbidden:
                await ctx.send(f"Unable to send message to ticket channel for {user.mention}")
            except Exception as e:
                logging.error(f"Error creating ticket channel for {user.name}: {e}")
        
    @bot.command(name='lunchprice')
    async def lunch_price(ctx):
        await ctx.send(f"Today's lunch price: {LUNCH_PRICE}")

    @bot.command(name='helpLunch')
    async def help_command(ctx):
        help_embed = discord.Embed(
            title="Lunch Bot Commands",
            color=discord.Color.blue()
        )
        help_embed.add_field(
            name="!comment <price> @user1 @user2 ...",
            value="Create or update lunch comment tickets for mentioned users with specified price",
            inline=False
        )
        help_embed.add_field(
            name="!setprice <price>",
            value="Set default lunch price (admin only)",
            inline=False
        )
        help_embed.add_field(
            name="!lunchprice",
            value="Show current lunch price",
            inline=False
        )
        await ctx.send(embed=help_embed)