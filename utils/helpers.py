import discord
from discord.utils import get

async def create_ticket_channel(guild, author, user):
    category = get(guild.categories, name="Lunch Tickets")
    if not category:
        category = await guild.create_category("Lunch Tickets")

    channel_name = f"ticket-{user.name}"  # Changed to include 'ticket-' prefix
    existing_channel = get(guild.text_channels, name=channel_name)
    if existing_channel:
        return existing_channel
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True),
        author: discord.PermissionOverwrite(read_messages=True),
        user: discord.PermissionOverwrite(read_messages=True)
    }

    ticket_channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        topic=f"Ticket for {user.name}",
        reason=f"Ticket created by {author.name} for {user.name}"
    )
    return ticket_channel

def create_lunch_ticket_embed(user, price, total_price, unpaid_count, current_date=None, updated=False):
    if updated:
        description = "Your lunch ticket has been updated."
        color = discord.Color.green()
    else:
        description = f"New lunch ticket for {user.mention}"
        color = discord.Color.blue()
    
    embed = discord.Embed(
        title="🍽️ Lunch Ticket",
        description=description,
        color=color
    )
    
    if not updated:
        embed.add_field(name="Date", value=current_date, inline=True)
        embed.add_field(name="Lunch Price", value=price, inline=True)
        embed.add_field(name="Total Unpaid Lunch", value=f"{total_price:.3f} VND", inline=True)
        embed.add_field(name="Unpaid Transactions", value=str(unpaid_count), inline=True)
        embed.add_field(
            name="Instructions", 
            value="1. Take a screenshot of your payment transaction\n2. Upload the payment screenshot and click 'Submit Payment Proof'\n3. Wait for admin verification",
            inline=False
        )
        embed.set_footer(text="Please complete the payment within 24 hours")
    else:
        embed.add_field(name="Total Unpaid Lunch", value=f"{total_price:.3f} VND", inline=True)
        embed.add_field(name="Unpaid Transactions", value=str(unpaid_count), inline=True)
        embed.add_field(
            name="Instructions", 
            value="1. Take a screenshot of your payment transaction\n2. Upload the payment screenshot and click 'Submit Payment Proof'\n3. Wait for admin verification",
            inline=False
        )
        embed.set_footer(text="Please complete the payment within 24 hours")
    
    return embed