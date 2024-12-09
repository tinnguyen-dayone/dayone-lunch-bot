import logging
from discord.ext import commands
import discord
import traceback
import sentry_sdk

# Create logger for events
event_logger = logging.getLogger('bot.events')

from utils.helpers import create_ticket_channel
from bot.views import image_store  

def setup_events(bot):
    if not getattr(bot, 'events_setup', False):
        @bot.event
        async def on_ready():
            logging.info(f'Logged in as {bot.user.name}')
            for guild in bot.guilds:
                category = discord.utils.get(guild.categories, name="Lunch Tickets")
                if not category:
                    await guild.create_category("Lunch Tickets")
            logging.info("All guilds are ready.")

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