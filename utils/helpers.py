import discord
from discord.utils import get
from database.manager import DatabaseManager
from config.settings import DB_URL
import pytz

db_manager = DatabaseManager(DB_URL)
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')

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
        table = "```\nDate/Time              Price      Status\n" + "-" * 45 + "\n"
        for date, price, confirmed in transactions:
            if not confirmed:  # Only show unpaid transactions
                # Convert UTC to Vietnam time
                local_date = date.astimezone(vietnam_tz)
                status = "unpaid"
                formatted_datetime = local_date.strftime("%Y-%m-%d %H:%M")
                table += f"{formatted_datetime:<20} {price:9} {status}\n"
        table += "-" * 45 + f"\nTotal: {total_price:.3f} VND"
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
    embed.set_footer(text="Please complete the payment within 24 hours")
    
    return embed