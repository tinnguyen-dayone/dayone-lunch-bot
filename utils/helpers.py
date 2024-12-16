import discord
from discord.utils import get
from database.manager import DatabaseManager
from config.settings import DB_URL, DB_MIN_CONNECTIONS, DB_MAX_CONNECTIONS  # Update imports
import pytz
import re

# Initialize database with pool settings
db_manager = DatabaseManager(
    DB_URL,
    min_conn=DB_MIN_CONNECTIONS,
    max_conn=DB_MAX_CONNECTIONS
)

vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')

async def create_ticket_channel(guild, author, user):
    category = get(guild.categories, name="Lunch Tickets")
    if not category:
        category = await guild.create_category("Lunch Tickets")

    # Simple channel name creation
    channel_name = f"ticket-{user.name}"

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
    title = "🍽️ Lunch Payment Details"
    description = f"Payment details for {user.mention}"
    color = discord.Color.blue()
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    
    # Get transaction history formatted as table
    transactions = db_manager.get_transaction_history(user.id)
    if transactions:
        table = "```\nDate/Time            Price     Status    Description\n" + "-" * 56 + "\n"
        for date, price, confirmed, desc in transactions:
            if not confirmed:  # Only show unpaid transactions
                local_date = date.astimezone(vietnam_tz)
                status = "unpaid"
                formatted_datetime = local_date.strftime("%Y-%m-%d %H:%M")
                description = desc[:20] + "..." if desc and len(desc) > 20 else (desc or "")
                table += f"{formatted_datetime:<20} {price:9} {status:9} {description}\n"
        table += "-" * 56 + f"\nTotal: {total_price:.3f} VND"
        table += "\n```"
        
        embed.add_field(
            name="Unpaid Transactions", 
            value=table,
            inline=False
        )
    
    embed.add_field(
        name="Instructions", 
        value="1. Take a screenshot of your payment transaction\n2. Upload the payment screenshot and click 'Submit Payment Proof'\n3. Wait for admin verification",
        inline=False
    )
    
    return embed