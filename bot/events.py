import logging
from discord.ext import commands
import discord
from utils.helpers import create_ticket_channel
from bot.views import user_last_image

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
            if isinstance(error, commands.errors.MissingPermissions):
                await ctx.send("You don't have permission to use this command!")
            elif isinstance(error, commands.errors.MemberNotFound):
                await ctx.send("Could not find that member!")
            else:
                logging.error(f"Command error: {str(error)}")
                await ctx.send("An error occurred while processing the command.")

        @bot.event
        async def on_message(message):
            # Check if the message is in a ticket channel
            if "ticket-" in message.channel.name and message.author != bot.user:
                if message.attachments:
                    user_id = message.author.id
                    user_last_image[user_id] = message.attachments[0]
                    logging.info(f"Image uploaded by user ID {user_id}.")
            await bot.process_commands(message)
        
        bot.events_setup = True