import logging
import psycopg2
from psycopg2.extras import DictCursor
import time

# Create logger for database operations
db_logger = logging.getLogger('bot.database')

class DatabaseManager:
    def __init__(self, db_url, retries=10, delay=5):  # Increased retries to 10
        """Initialize database connection with retries"""
        self.db_url = db_url
        for attempt in range(1, retries + 1):
            try:
                self.conn = psycopg2.connect(self.db_url)
                logging.info("Database connection established.")
                break
            except psycopg2.OperationalError as e:
                logging.error(f"Attempt {attempt}: Failed to connect to the database: {e}")
                if attempt < retries:
                    logging.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logging.error("All retry attempts failed.")
                    raise
        self.create_tables()

    def create_tables(self):
        """Create necessary database tables"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    total_unpaid NUMERIC DEFAULT 0.0
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    commented_count INTEGER DEFAULT 0,
                    lunch_price TEXT,
                    total_price NUMERIC DEFAULT 0.0,
                    transaction_image TEXT,
                    transaction_confirmed BOOLEAN DEFAULT FALSE,
                    transaction_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    paid BOOLEAN DEFAULT FALSE,
                    ticket_message_id BIGINT
                )
            ''')
            self.conn.commit()
            logging.info("Database tables are set up successfully.")
        except Exception as e:
            logging.error(f"Error creating tables: {e}")
            self.conn.rollback()
            raise

    def add_or_get_user(self, user_id):
        """Add a new user or get existing user"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO users (user_id)
                VALUES (%s)
                ON CONFLICT (user_id) DO NOTHING
            ''', (user_id,))
            self.conn.commit()

    def create_transaction(self, user_id, price):
        """Create a new transaction for a user"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO transactions (user_id, lunch_price, total_price, commented_count)
                VALUES (%s, %s, %s, 1)
                RETURNING transaction_id
            ''', (user_id, price, self._extract_numeric(price)))
            transaction_id = cursor.fetchone()[0]
            cursor.execute('''
                UPDATE users
                SET total_unpaid = total_unpaid + %s
                WHERE user_id = %s
            ''', (self._extract_numeric(price), user_id))
        self.conn.commit()
        return transaction_id

    def update_transaction(self, transaction_id, image_url):
        """Update transaction image and mark as submitted"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET transaction_image = %s, transaction_date = CURRENT_TIMESTAMP, paid = FALSE
                WHERE transaction_id = %s
            ''', (image_url, transaction_id))
        self.conn.commit()

    def confirm_transaction(self, transaction_id):
        """Mark transaction as confirmed and paid"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET transaction_confirmed = TRUE,
                    paid = TRUE
                WHERE transaction_id = %s
            ''', (transaction_id,))
            # Update user's total unpaid
            cursor.execute('''
                SELECT total_price FROM transactions WHERE transaction_id = %s
            ''', (transaction_id,))
            total_price = cursor.fetchone()[0]
            cursor.execute('''
                UPDATE users
                SET total_unpaid = total_unpaid - %s
                WHERE user_id = (
                    SELECT user_id FROM transactions WHERE transaction_id = %s
                )
            ''', (total_price, transaction_id))
        self.conn.commit()

    def increment_commentation_with_price(self, user_id, price):
        """Add a new transaction with the given price"""
        try:
            db_logger.debug(f'Adding new transaction for user {user_id} with price {price}')
            self.add_or_get_user(user_id)
            transaction_id = self.create_transaction(user_id, price)
            db_logger.info(f'Successfully created transaction {transaction_id} for user {user_id}')
            return transaction_id
        except Exception as e:
            db_logger.error(f'Failed to create transaction for user {user_id}: {str(e)}\n{traceback.format_exc()}')
            raise

    def set_ticket_message_id(self, transaction_id, message_id):
        """Set the ticket message ID for a transaction"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET ticket_message_id = %s
                WHERE transaction_id = %s
            ''', (message_id, transaction_id))
        self.conn.commit()

    def get_ticket_message_id(self, transaction_id):
        """Retrieve the ticket message ID for a transaction"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                SELECT ticket_message_id
                FROM transactions 
                WHERE transaction_id = %s
            ''', (transaction_id,))
            result = cursor.fetchone()
            return result[0] if result else None

    def get_user_transactions(self, user_id):
        """Retrieve all transactions for a user"""
        with self.conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute('''
                SELECT * FROM transactions
                WHERE user_id = %s AND paid = FALSE
                ORDER BY transaction_date DESC
            ''', (user_id,))
            return cursor.fetchall()

    def get_transaction_details(self, transaction_id):
        """Get details of a specific transaction"""
        with self.conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute('''
                SELECT * FROM transactions
                WHERE transaction_id = %s
            ''', (transaction_id,))
            return cursor.fetchone()

    def has_unpaid_transactions(self, user_id):
        """Check if the user has any unpaid transactions"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                SELECT 1 FROM transactions
                WHERE user_id = %s AND paid = FALSE
                LIMIT 1
            ''', (user_id,))
            return cursor.fetchone() is not None

    def _extract_numeric(self, price_str):
        """Extract numeric value from price string"""
        numeric_price = ''.join(filter(lambda x: x.isdigit() or x == '.', price_str))
        try:
            return float(numeric_price)
        except ValueError:
            logging.error(f"Invalid price format: {price_str}")
            return 0.0

    def reset_user_data(self, user_id):
        """Reset all data for a user"""
        with self.conn.cursor() as cursor:
            cursor.execute('DELETE FROM transactions WHERE user_id = %s', (user_id,))
            cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
        self.conn.commit()

    def get_unpaid_transactions(self):
        """Get all unpaid transactions"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                SELECT user_id, commented_count, lunch_price
                FROM transactions 
                WHERE paid = FALSE
            ''')
            return cursor.fetchall()

    def get_transaction_history(self, user_id):
        """Get transaction history for user"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                SELECT transaction_date, lunch_price, transaction_confirmed
                FROM transactions 
                WHERE user_id = %s AND transaction_date IS NOT NULL
                ORDER BY transaction_date DESC
            ''', (user_id,))
            return cursor.fetchall()

    def has_ticket(self, user_id):
        """Check if the user has an existing ticket"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                SELECT 1 FROM transactions 
                WHERE user_id = %s AND paid = FALSE
            ''', (user_id,))
            return cursor.fetchone() is not None

    def get_unpaid_total(self, user_id):
        """Calculate the total unpaid transactions for a user"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                SELECT SUM(total_price) 
                FROM transactions
                WHERE user_id = %s AND paid = FALSE
            ''', (user_id,))
            result = cursor.fetchone()
            return float(result[0]) if result and result[0] else 0.0

    def get_unpaid_count(self, user_id):
        """Get the count of unpaid transactions for a user"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                SELECT COUNT(*) 
                FROM transactions
                WHERE user_id = %s AND paid = FALSE
            ''', (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 0

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

    def __del__(self):
        """Destructor to ensure database connection is closed"""
        self.close()

    def get_user_ticket_message_ids(self, user_id):
        """Retrieve all ticket message IDs for a user's unpaid transactions"""
        with self.conn.cursor() as cursor:
            cursor.execute('''
                SELECT ticket_message_id
                FROM transactions
                WHERE user_id = %s AND paid = FALSE AND ticket_message_id IS NOT NULL
            ''', (user_id,))
            results = cursor.fetchall()
            return [row[0] for row in results]