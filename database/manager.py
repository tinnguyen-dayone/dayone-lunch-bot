import logging
import traceback
import psycopg2
from psycopg2 import pool
from psycopg2.extras import DictCursor
import time
import sentry_sdk
from functools import wraps

# Create logger for database operations
db_logger = logging.getLogger('bot.database')

class DatabaseManager:
    _instance = None
    _pool = None
    
    def __new__(cls, db_url, min_conn=1, max_conn=10):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialize_pool(db_url, min_conn, max_conn)
        return cls._instance

    def _initialize_pool(self, db_url, min_conn, max_conn):
        """Initialize the connection pool"""
        try:
            self._pool = pool.ThreadedConnectionPool(
                minconn=min_conn,
                maxconn=max_conn,
                dsn=db_url
            )
            db_logger.info("Connection pool initialized successfully")
        except Exception as e:
            db_logger.error(f"Failed to initialize connection pool: {e}")
            raise

    def get_connection(self):
        """Get a connection from the pool"""
        return self._pool.getconn()

    def return_connection(self, conn):
        """Return a connection to the pool"""
        self._pool.putconn(conn)

    def with_connection(func):
        """Decorator to handle database connections from pool"""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            conn = None
            try:
                conn = self.get_connection()
                if 'conn' in kwargs:
                    del kwargs['conn']  # Remove conn if it exists in kwargs
                return func(self, *args, conn=conn, **kwargs)
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                db_logger.error(f"Database connection error in {func.__name__}: {e}")
                if conn:
                    conn.rollback()
                raise
            except Exception as e:
                db_logger.error(f"Error in {func.__name__}: {e}")
                if conn:
                    conn.rollback()
                raise
            finally:
                if conn:
                    try:
                        self.return_connection(conn)
                    except Exception as e:
                        db_logger.error(f"Error returning connection to pool: {e}")

        return wrapper

    # Modify all database methods to use the connection pool
    @with_connection
    def create_tables(self, conn=None):
        """Create necessary database tables"""
        try:
            with conn.cursor() as cursor:
                # Add description column to transactions table
                cursor.execute('''
                    ALTER TABLE transactions 
                    ADD COLUMN IF NOT EXISTS description TEXT
                ''')
                
                # Create users table first
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        total_unpaid NUMERIC DEFAULT 0.0
                    )
                ''')
                
                # Create transactions table with foreign key reference
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
                        ticket_message_id BIGINT,
                        description TEXT
                    )
                ''')
                
                # Add any necessary indexes
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
                    CREATE INDEX IF NOT EXISTS idx_transactions_paid ON transactions(paid);
                ''')
                
                conn.commit()
                db_logger.info("Database tables and indexes created successfully")
        except Exception as e:
            conn.rollback()
            db_logger.error(f"Error creating database tables: {e}")
            raise

    # Modify other methods similarly to use the connection parameter
    # Example:
    @with_connection
    def add_or_get_user(self, user_id, username=None, conn=None):
        """Add a new user or update existing user's username"""
        try:
            with conn.cursor() as cursor:
                if username:  # Only update if username is provided
                    cursor.execute('''
                        INSERT INTO users (user_id, username)
                        VALUES (%s, %s)
                        ON CONFLICT (user_id) 
                        DO UPDATE SET username = EXCLUDED.username
                        RETURNING username
                    ''', (user_id, username))
                else:
                    cursor.execute('''
                        INSERT INTO users (user_id)
                        VALUES (%s)
                        ON CONFLICT (user_id) DO NOTHING
                        RETURNING username
                    ''', (user_id,))
                result = cursor.fetchone()
                conn.commit()
                return result[0] if result else None
        except Exception as e:
            sentry_sdk.capture_exception()
            db_logger.error(f"Error in add_or_get_user: {e}")
            conn.rollback()
            raise

    @with_connection
    def create_transaction(self, user_id, price, conn=None):
        """Create a new transaction for a user"""
        with conn.cursor() as cursor:
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
            conn.commit()
            return transaction_id

    @with_connection
    def update_transaction(self, transaction_id, image_url, conn=None):
        """Update transaction image and mark as submitted"""
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET transaction_image = %s, transaction_date = CURRENT_TIMESTAMP, paid = FALSE
                WHERE transaction_id = %s
            ''', (image_url, transaction_id))
        conn.commit()

    @with_connection
    def confirm_transaction(self, transaction_id, conn=None):
        """Mark transaction as confirmed and paid"""
        with conn.cursor() as cursor:
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
        conn.commit()

    @with_connection
    def confirm_all_user_transactions(self, user_id, conn=None):
        """Mark all unpaid transactions for a user as confirmed and paid"""
        with conn.cursor() as cursor:
            # Update all unpaid transactions
            cursor.execute('''
                UPDATE transactions
                SET transaction_confirmed = TRUE,
                    paid = TRUE
                WHERE user_id = %s AND paid = FALSE
            ''', (user_id,))
            
            # Reset user's total unpaid amount
            cursor.execute('''
                UPDATE users
                SET total_unpaid = 0
                WHERE user_id = %s
            ''', (user_id,))
        conn.commit()
        logging.info(f"All unpaid transactions confirmed for user {user_id}")

    @with_connection
    def increment_commentation_with_price(self, user_id, price, description=None, conn=None):
        """Add a new transaction with the given price and description"""
        try:
            db_logger.debug(f'Adding new transaction for user {user_id} with price {price}')
            # Pass the connection directly to methods
            with conn.cursor() as cursor:
                # Inline the add_or_get_user logic to avoid connection conflicts
                cursor.execute('''
                    INSERT INTO users (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO NOTHING
                    RETURNING username
                ''', (user_id,))
                
                # Create transaction using the same connection
                cursor.execute('''
                    INSERT INTO transactions (user_id, lunch_price, total_price, commented_count, description)
                    VALUES (%s, %s, %s, 1, %s)
                    RETURNING transaction_id
                ''', (user_id, price, self._extract_numeric(price), description))
                transaction_id = cursor.fetchone()[0]
                
                # Update user's total unpaid
                cursor.execute('''
                    UPDATE users
                    SET total_unpaid = total_unpaid + %s
                    WHERE user_id = %s
                ''', (self._extract_numeric(price), user_id))
                
                conn.commit()
                db_logger.info(f'Successfully created transaction {transaction_id} for user {user_id}')
                return transaction_id
                
        except Exception as e:
            conn.rollback()
            db_logger.error(f'Failed to create transaction for user {user_id}: {str(e)}\n{traceback.format_exc()}')
            raise

    @with_connection
    def set_ticket_message_id(self, transaction_id, message_id, conn=None):
        """Set the ticket message ID for a transaction"""
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET ticket_message_id = %s
                WHERE transaction_id = %s
            ''', (message_id, transaction_id))
        conn.commit()

    @with_connection
    def get_ticket_message_id(self, transaction_id, conn=None):
        """Retrieve the ticket message ID for a transaction"""
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT ticket_message_id
                FROM transactions 
                WHERE transaction_id = %s
            ''', (transaction_id,))
            result = cursor.fetchone()
            return result[0] if result else None

    @with_connection
    def get_user_transactions(self, user_id, conn=None):
        """Retrieve all transactions for a user"""
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute('''
                SELECT transaction_id, transaction_date, lunch_price, total_price, 
                       transaction_confirmed, paid, description
                FROM transactions
                WHERE user_id = %s AND paid = FALSE
                ORDER BY transaction_date DESC
            ''', (user_id,))
            return cursor.fetchall()

    @with_connection
    def get_transaction_details(self, transaction_id, conn=None):
        """Get details of a specific transaction"""
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute('''
                SELECT transaction_id, user_id, lunch_price, total_price, 
                       transaction_image, transaction_confirmed, transaction_date,
                       paid, ticket_message_id, description
                FROM transactions
                WHERE transaction_id = %s
            ''', (transaction_id,))
            return cursor.fetchone()

    @with_connection
    def has_unpaid_transactions(self, user_id, conn=None):
        """Check if the user has any unpaid transactions"""
        with conn.cursor() as cursor:
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

    @with_connection
    def reset_user_data(self, user_id, conn=None):
        """Reset all data for a user"""
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM transactions WHERE user_id = %s', (user_id,))
            cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
        conn.commit()

    @with_connection
    def get_unpaid_transactions(self, conn=None):
        """Get all unpaid transactions"""
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT user_id, commented_count, lunch_price, description
                FROM transactions 
                WHERE paid = FALSE
            ''')
            return cursor.fetchall()

    @with_connection
    def get_transaction_history(self, user_id, conn=None):
        """Get unpaid transaction history for user"""
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT transaction_date, lunch_price, transaction_confirmed, description
                FROM transactions 
                WHERE user_id = %s 
                AND transaction_date IS NOT NULL
                AND paid = FALSE
                ORDER BY transaction_date DESC
            ''', (user_id,))
            return cursor.fetchall()

    @with_connection
    def has_ticket(self, user_id, conn=None):
        """Check if the user has an existing ticket"""
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT 1 FROM transactions 
                WHERE user_id = %s AND paid = FALSE
            ''', (user_id,))
            return cursor.fetchone() is not None

    @with_connection
    def get_unpaid_total(self, user_id, conn=None):
        """Calculate the total unpaid transactions for a user"""
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT SUM(total_price) 
                FROM transactions
                WHERE user_id = %s AND paid = FALSE
            ''', (user_id,))
            result = cursor.fetchone()
            return float(result[0]) if result and result[0] else 0.0

    @with_connection
    def get_unpaid_count(self, user_id, conn=None):
        """Get the count of unpaid transactions for a user"""
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT COUNT(*) 
                FROM transactions
                WHERE user_id = %s AND paid = FALSE
            ''', (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 0

    def close(self):
        """Close the connection pool"""
        if self._pool:
            self._pool.closeall()
            db_logger.info("Connection pool closed")

    def __del__(self):
        """Ensure pool is closed on deletion"""
        self.close()

    @with_connection
    def get_user_ticket_message_ids(self, user_id, conn=None):
        """Retrieve all ticket message IDs for a user's unpaid transactions"""
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT ticket_message_id
                FROM transactions
                WHERE user_id = %s AND paid = FALSE AND ticket_message_id IS NOT NULL
            ''', (user_id,))
            results = cursor.fetchall()
            return [row[0] for row in results]

    @with_connection
    def get_transaction_by_message_id(self, message_id, conn=None):
        """Get transaction details by message ID"""
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute('''
                SELECT *
                FROM transactions
                WHERE ticket_message_id = %s AND paid = FALSE
            ''', (message_id,))
            return cursor.fetchone()

    @with_connection
    def clean_deleted_message_refs(self, message_ids, conn=None):
        """Clean up deleted message references from database"""
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions 
                SET ticket_message_id = NULL
                WHERE ticket_message_id = ANY(%s)
                AND paid = FALSE
            ''', (message_ids,))
        conn.commit()
        logging.info(f"Cleaned up {len(message_ids)} deleted message references")

    @with_connection
    def get_active_tickets(self, conn=None):
        """Get all active (unpaid) transactions with their message IDs"""
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute('''
                SELECT DISTINCT ON (t.user_id) 
                    t.*, u.username,
                    t.description
                FROM transactions t
                JOIN users u ON t.user_id = u.user_id
                WHERE t.paid = FALSE 
                AND t.ticket_message_id IS NOT NULL
                ORDER BY t.user_id, t.transaction_date DESC
            ''')
            return cursor.fetchall()

    @with_connection
    def get_latest_unpaid_transaction(self, user_id, conn=None):
        """Get user's latest unpaid transaction"""
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute('''
                SELECT *,
                       description
                FROM transactions
                WHERE user_id = %s 
                AND paid = FALSE
                AND ticket_message_id IS NOT NULL
                ORDER BY transaction_date DESC
                LIMIT 1
            ''', (user_id,))
            return cursor.fetchone()