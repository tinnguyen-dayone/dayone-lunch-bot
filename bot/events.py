import logging
from discord.ext import commands
import discord
import traceback
import sentry_sdk

# Create logger for events
event_logger = logging.getLogger('bot.events')

from utils.helpers import create_ticket_channel
from bot.views import image_store, PaymentView
from database.manager import DatabaseManager
from config.settings import DB_URL, DB_MIN_CONNECTIONS, DB_MAX_CONNECTIONS  # Update imports

# Initialize database with pool settings
db_manager = DatabaseManager(
    DB_URL,
    min_conn=DB_MIN_CONNECTIONS,
    max_conn=DB_MAX_CONNECTIONS
)

def setup_events(bot):
    async def process_ticket(ticket):
        """Process a single ticket and restore its view"""
        try:
            # Use bot instance passed to setup_events
            for guild in bot.guilds:
                user = guild.get_member(ticket['user_id'])
                if user:
                    # Remove leading dot when looking for channel name
                    username = ticket['username']
                    if username.startswith('.'):
                        username = username[1:]
                    channel_name = f"ticket-{username}"
                    channel = discord.utils.get(guild.channels, name=channel_name)
                    
                    if not channel:  # Try with lowercase if not found
                        channel_name = f"ticket-{username.lower()}"
                        channel = discord.utils.get(guild.channels, name=channel_name)
                    
                    if channel and isinstance(channel, discord.TextChannel):
                        try:
                            message = await channel.fetch_message(ticket['ticket_message_id'])
                            if message:
                                # Find an admin
                                admin = None
                                for member in channel.members:
                                    member_perms = channel.permissions_for(member)
                                    if (member_perms.administrator or member_perms.manage_messages) and member != bot.user:
                                        admin = member
                                        break
                                
                                if admin:
                                    view = PaymentView(user, channel, admin, ticket['transaction_id'])
                                    await message.edit(view=view)
                                    bot.add_view(view)
                                    logging.info(f"Restored view for ticket {ticket['transaction_id']}")
                                else:
                                    logging.warning(f"No admin found for channel {channel.name}")
                        except discord.NotFound:
                            logging.warning(f"Message {ticket['ticket_message_id']} not found in {channel.name}")
                        except Exception as e:
                            logging.error(f"Error processing message: {e}")
                    else:
                        logging.warning(f"Channel ticket-{ticket['username']} not found")
                    break

        except Exception as e:
            logging.error(f"Error processing ticket {ticket['transaction_id']}: {e}")
            raise

    if not getattr(bot, 'events_setup', False):
        @bot.event
        async def on_ready():
            logging.info(f'Logged in as {bot.user.name}')
            
            try:
                # Get all active tickets in a single transaction
                active_tickets = db_manager.get_active_tickets()
                logging.info(f"Found {len(active_tickets)} active tickets")
                logging.info("Bot is ready to process tickets.")
                
                # Process each ticket
                for ticket in active_tickets:
                    try:
                        await process_ticket(ticket)
                    except Exception as e:
                        logging.error(f"Error processing ticket {ticket['transaction_id']}: {e}")
                        continue
                        
            except Exception as e:
                logging.error(f"Error in on_ready: {e}")

        @bot.event
        async def on_command_error(ctx, error):
            # Set Sentry context
            with sentry_sdk.configure_scope() as scope:
                scope.set_user({"id": ctx.author.id, "username": str(ctx.author)})
                scope.set_context("command", {
                    "name": ctx.command.name if ctx.command else "Unknown",
                    "channel": str(ctx.channel),
                    "guild": str(ctx.guild)
                })
                
                if isinstance(error, commands.CommandInvokeError):
                    event_logger.error(f"Command error in {ctx.command}: {error.__cause__}")
                    sentry_sdk.capture_exception(error.__cause__)
                    return

                # Handle other errors
                if isinstance(error, commands.errors.MissingPermissions):
                    await ctx.send("You don't have permission to use this command!")
                elif isinstance(error, commands.errors.MemberNotFound):
                    await ctx.send("Could not find that member!")
                else:
                    event_logger.error(f"Unhandled error: {error}")
                    sentry_sdk.capture_exception(error)

        @bot.event
        async def on_error(event, *args, **kwargs):
            sentry_sdk.capture_message(
                f"Discord event error in {event}",
                level="error",
                extras={
                    "args": args,
                    "kwargs": kwargs
                }
            )
            event_logger.error(f"Error in {event}: {traceback.format_exc()}")

        @bot.event
        async def on_message(message):
            # Check if the message is not in a DM channel
            if not isinstance(message.channel, discord.DMChannel):
                # Only proceed if it's a ticket channel
                if "ticket-" in message.channel.name and message.author != bot.user:
                    if message.attachments:
                        user_id = message.author.id
                        await image_store.set_image(user_id, message.attachments[0])  # Use image_store instead
                        logging.info(f"Image uploaded by user ID {user_id}.")
            await bot.process_commands(message)
        
        bot.events_setup = True

        @bot.event
        async def on_shutdown():
            logging.info("Shutting down the bot...")
            db_manager.close()