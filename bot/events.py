import logging
from discord.ext import commands
import discord
import traceback
import sentry_sdk

# Create logger for events
event_logger = logging.getLogger('bot.events')

from utils.helpers import create_ticket_channel
from bot.views import image_store, PaymentView
from database.manager import DatabaseManager  # Add this import
from config.settings import DB_URL  # Add this import

# Add database manager instance
db_manager = DatabaseManager(DB_URL)

def setup_events(bot):
    if not getattr(bot, 'events_setup', False):
        @bot.event
        async def on_ready():
            logging.info(f'Logged in as {bot.user.name}')
            
            # Get all active tickets from database
            active_tickets = db_manager.get_active_tickets()
            logging.info(f"Found {len(active_tickets)} active tickets in database")
            restored_count = 0
            deleted_messages = []
            
            for guild in bot.guilds:
                # Set up category if needed
                category = discord.utils.get(guild.categories, name="Lunch Tickets")
                if not category:
                    await guild.create_category("Lunch Tickets")
                
                # Find all ticket channels and store them in a dictionary
                ticket_channels = {}
                for channel in guild.channels:
                    if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
                        # Store both the exact name and a normalized version
                        ticket_channels[channel.name.lower()] = channel
                        normalized_name = ''.join(c.lower() for c in channel.name if c.isalnum())
                        ticket_channels[normalized_name] = channel
                        logging.info(f"Found ticket channel: {channel.name}")
                
                logging.info(f"Found {len(ticket_channels)} ticket channels")
                
                # Process active tickets
                for transaction in active_tickets:
                    try:
                        username = transaction['username']
                        # Generate possible channel name variations
                        possible_channel_names = [
                            f"ticket-{username}".lower(),
                            f"ticket-{username.replace(' ', '')}".lower(),
                            f"ticket-{username.replace(' ', '_')}".lower(),
                            ''.join(c.lower() for c in f"ticket-{username}" if c.isalnum())
                        ]
                        
                        logging.info(f"Looking for channel with possible names: {possible_channel_names}")
                        
                        channel = None
                        for channel_name in possible_channel_names:
                            if channel_name in ticket_channels:
                                channel = ticket_channels[channel_name]
                                logging.info(f"Found matching channel: {channel.name}")
                                break
                        
                        if channel:
                            message_id = transaction['ticket_message_id']
                            if not message_id:
                                logging.warning(f"No message ID found for transaction in channel {channel.name}")
                                continue
                                
                            logging.info(f"Processing message ID {message_id} in channel {channel.name}")
                            
                            try:
                                message = await channel.fetch_message(message_id)
                                if message:
                                    # Get user from transaction details
                                    user = guild.get_member(transaction['user_id'])
                                    
                                    # Find all admins in the channel
                                    admins = []
                                    for member in channel.members:
                                        # Check for both administrator permission and manage messages permission
                                        member_perms = channel.permissions_for(member)
                                        if (member_perms.administrator or 
                                            member_perms.manage_messages) and member != bot.user:
                                            admins.append(member)
                                            logging.info(f"Found admin in channel: {member.name}")
                                    
                                    # Use the original command author as admin if available
                                    admin = None
                                    for admin_member in admins:
                                        if admin_member.id == transaction.get('admin_id'):
                                            admin = admin_member
                                            break
                                    
                                    # If original admin not found, use first available admin
                                    if not admin and admins:
                                        admin = admins[0]
                                    
                                    if user and admin:
                                        view = PaymentView(user, channel, admin, transaction['transaction_id'])
                                        await message.edit(view=view)
                                        bot.add_view(view)
                                        restored_count += 1
                                        logging.info(f"Successfully restored view for transaction {transaction['transaction_id']} with admin {admin.name}")
                                    else:
                                        logging.warning(f"Could not restore view: user={user is not None}, admin={admin is not None}")
                            except discord.NotFound:
                                deleted_messages.append(message_id)
                                logging.warning(f"Message {message_id} not found in {channel.name}")
                            except Exception as e:
                                logging.error(f"Error processing message {message_id}: {str(e)}")
                        else:
                            logging.warning(f"No matching channel found for username: {username}")
                    except Exception as e:
                        logging.error(f"Error processing transaction {transaction['transaction_id']}: {str(e)}")
                        continue

            # Clean up deleted message references
            if deleted_messages:
                db_manager.clean_deleted_message_refs(deleted_messages)

            logging.info(f"Successfully restored {restored_count} payment views")

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