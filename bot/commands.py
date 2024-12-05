from discord.ext import commands
import discord  # Added import
import logging
from database.manager import DatabaseManager
from config.settings import DB_URL, LUNCH_PRICE
from utils.helpers import create_ticket_channel, create_lunch_ticket_embed
from bot.views import PaymentView
from datetime import datetime
import traceback
from typing import List

# Create logger for commands
cmd_logger = logging.getLogger('bot.commands')

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

    @bot.command(name='lunch')
    async def lunch(ctx, price: str, *users: discord.Member):
        cmd_logger.info(f'Lunch command initiated by {ctx.author} for {len(users)} users with price {price}')
        
        try:
            # Permission check
            if not ctx.author.guild_permissions.administrator:
                await ctx.send("You don't have permission to use this command!")
                return

            if not users:
                await ctx.send("Please mention at least one user!")
                return

            # Price validation with error handling
            try:
                numeric_price = ''.join(filter(lambda x: x.isdigit() or x == '.', price))
                float_price = float(numeric_price)
                if float_price <= 0:
                    raise ValueError("Price must be positive")
            except ValueError:
                await ctx.send("Invalid price format. Please use a positive numeric value like '55.000 VND'.")
                return

            processed_users = []
            failed_users = []

            for user in users:
                try:
                    cmd_logger.debug(f'Processing comment for user {user.name} with price {price}')
                
                    # Create transaction first to ensure database consistency
                    transaction_id = db_manager.increment_commentation_with_price(user.id, price)
                    if not transaction_id:
                        raise Exception("Failed to create transaction")

                    # Get totals after transaction creation
                    total_unpaid = db_manager.get_unpaid_total(user.id)
                    unpaid_count = db_manager.get_unpaid_count(user.id)

                    # Create or get ticket channel
                    ticket_channel = await create_ticket_channel(ctx.guild, ctx.author, user)
                    if not ticket_channel:
                        raise Exception("Could not create ticket channel")

                    # Delete old tickets
                    old_messages = db_manager.get_user_ticket_message_ids(user.id)
                    for msg_id in old_messages:
                        try:
                            old_msg = await ticket_channel.fetch_message(msg_id)
                            await old_msg.delete()
                        except (discord.NotFound, discord.Forbidden):
                            pass

                    # Create new embed and send
                    embed = create_lunch_ticket_embed(
                        user, price, total_unpaid, unpaid_count,
                        current_date=datetime.now().strftime("%Y-%m-%d")
                    )
                
                    sent_message = await ticket_channel.send(
                        embed=embed,
                        view=PaymentView(user, ticket_channel, ctx.author, transaction_id)
                    )
                
                    # Store new message ID
                    db_manager.set_ticket_message_id(transaction_id, sent_message.id)
                    processed_users.append(user.name)
                    cmd_logger.info(f"Successfully processed comment for {user.name}")

                except Exception as user_error:
                    cmd_logger.error(f"Error processing user {user.name}: {str(user_error)}\n{traceback.format_exc()}")
                    failed_users.append(f"{user.name} ({str(user_error)})")

            # Only send success/failure messages if we processed any users
            if processed_users:
                await ctx.send(f"✅ Successfully add lunch price for: {', '.join(processed_users)}")
            if failed_users:
                await ctx.send(f"❌ Failed to process: {', '.join(failed_users)}")

        except Exception as e:
            cmd_logger.error(f"Critical error in lunch command: {str(e)}\n{traceback.format_exc()}")
            await ctx.send(f"A critical error occurred: {str(e)}")

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
            name="!lunch <price> @user1 @user2 ...",
            value="Create or update lunch tickets for mentioned users with specified price",
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