import datetime
import json
import os
from pathlib import Path
from typing import Optional, List, Tuple

import psycopg2

from psycopg2 import extensions


class SQLHistoryWriter:
    """
    A class to manage the ConversationHistory database.

    Args:
        host: PostgreSQL Database host.
        port: PostgreSQL Database port.
        user: PostgreSQL Database user.
        password: PostgreSQL Database user password.
        database: PostgreSQL Database name.
        **kwargs: Additional arguments to pass to psycopg2.connect.
    """

    def __init__(
            self,
            host: str,
            port: str,
            user: str,
            password: str,
            database: str,
            **kwargs
    ) -> None:
        self._connection = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            **kwargs
        )

        self._connection_params = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database,
            **kwargs
        }

        self._create_history_table()
        self._create_checkpoints_table()
        self._create_payment_table()
        print("Database Conversations created")

    def _connect(self):
        self._connection = psycopg2.connect(**self._connection_params)

    @property
    def connection(self) -> psycopg2.extensions.connection:
        try:
            self._connection.cursor().execute('SELECT 1')
            return self._connection
        except psycopg2.InterfaceError:
            self._connection.close()
            self._connect()
            return self._connection

    @classmethod
    def from_config(cls, file_path: Path) -> "SQLHistoryWriter":
        """
        Load the database configuration from a JSON file.

        Args:
            file_path: Path to JSON file.
        """
        data = json.loads(file_path.read_text())
        return cls(**data)

    def _create_history_table(self) -> None:
        """
        Create the ConversationHistory database.
        """
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ConversationHistory (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,                
                user_message TEXT,
                chatbot_message TEXT,
                timestamp TIMESTAMP
                )
                """
            )
        self._connection.commit()

    def write_message(
            self,
            user_id: str,
            user_message: str,
            chatbot_message: str,
            timestamp: Optional[str] = None,
    ) -> None:
        """
        Add a new row to the ConversationHistory table.

        Args:
            user_id: ID of the user who sent the message.
            user_message: Message sent by the user.
            chatbot_message: Message sent by the chatbot.
            env: Environment where the message was sent (default: PROD_ENV).
            timestamp: Timestamp for the message.
        """
        timestamp = (
            timestamp
            if timestamp
            else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ConversationHistory (user_id, user_message, chatbot_message, timestamp)
                    VALUES (%s, %s, %s, to_timestamp(%s, 'YYYY-MM-DD HH24:MI:SS'))
                    """,
                    (
                        user_id,
                        user_message,
                        chatbot_message,
                        timestamp,
                    ),
                )
            self._connection.commit()

        except psycopg2.InterfaceError:
            self._connection.close()
            self._connection = psycopg2.connect(**self._connection_params)
            self.write_message(
                user_id, user_message, chatbot_message, timestamp
            )

    import json

    def write_checkpoint(
            self,
            user_id: str,
            history: List[dict],
            memory_moving_summary_buffer: str
    ) -> None:
        """
        Add a new row to the ConversationCheckpoints table or update an existing row.

        Parameters:
            user_id (str): The unique identifier of the user.
            history (List[dict]): The history data to be stored as a list of dictionaries.
            memory_moving_summary_buffer (str): The memory_moving_summary_buffer data to be stored.
        """
        try:
            # Convert the history list to a JSON-formatted string
            history_json = json.dumps(history)

            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ConversationCheckpoints
                SET history = %s::jsonb,
                    memory_moving_summary_buffer = %s
                WHERE user_id = %s
                    """,
                    (history_json, memory_moving_summary_buffer, user_id)
                )

            self._connection.commit()

        except psycopg2.InterfaceError:
            self._connection.close()
            self._connection = psycopg2.connect(**self._connection_params)
            self.write_checkpoint(user_id, history, memory_moving_summary_buffer)

    def _create_checkpoints_table(self) -> None:
        """
        Create the Companions table.
        """
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ConversationCheckpoints (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,                    
                    history JSONB,
                    memory_moving_summary_buffer TEXT                              
                )
                """
            )
        self._connection.commit()

    def _create_payment_table(self) -> None:
        """
        Create the payment table.
        """
        with self._connection.cursor() as cursor:
            create_table_query = '''
                CREATE TABLE IF NOT EXISTS payment (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    client_secret VARCHAR(255) NOT NULL,
                    client_email VARCHAR(255) NOT NULL,
                    subscription_id VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                )
            '''
            cursor.execute(create_table_query)
        self._connection.commit()

    def create_new_user(self, user_id) -> None:
        """
        Create a new user in the database.
        """
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    f"""
                        INSERT INTO ConversationCheckpoints (
                            user_id,                                                    
                            history,
                            memory_moving_summary_buffer                           
                        )
                        VALUES (
                            %(user_id)s,                                                        
                            %(history)s,
                            %(memory_moving_summary_buffer)s                            
                        )
                        """,
                    {"user_id": user_id,
                     "history": str([]),
                     "memory_moving_summary_buffer": "",
                     })
                self._connection.commit()  # Commit the changes to the database
        except psycopg2.InterfaceError:
            self._connection.close()
            self._connection = psycopg2.connect(**self._connection_params)
            self.create_new_user(user_id)

    def delete_user_history(self, user_id) -> None:
        """
        Delete a user's history from the database.
        """
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM ConversationCheckpoints
                    WHERE user_id = %(user_id)s;
                    """,
                    {"user_id": user_id}
                )
                self._connection.commit()  # Commit the changes to the database
        except psycopg2.InterfaceError:
            self._connection.close()
            self._connection = psycopg2.connect(**self._connection_params)
            self.delete_user_history(user_id)


    def get_all_messages_companions(self):
        """
        Returns a list of all messages in the ConversationHistory table.
        """
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM Companions
                """
            )
            rows = cursor.fetchall()
        return rows

    def get_all_messages(self):
        """
        Returns a list of all messages in the ConversationHistory table.
        """
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM ConversationHistory
                """
            )
            rows = cursor.fetchall()
        return rows

    def get_chat_history(
            self,
            user_id: int
    ) -> List[dict]:
        """
        Retrieve the chat history for a given conversation_id and user_id.

        Args:
            conversation_id: Unique ID for the conversation.
            user_id: ID of the user.

        Returns:
            A list of tuples, where each tuple represents a message in the conversation.
            The tuple contains the following fields:
            - user_id: ID of the user who sent the message.
            - message: The text of the message.
            - is_user: True if the message was sent by the user, False if sent by the chatbot.
            - timestamp: The timestamp of the message.
        """

        messages = []
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, user_message, chatbot_message, timestamp
                FROM ConversationHistory
                WHERE user_id = %s
                ORDER BY timestamp ASC
                """,
                (user_id)
            )
            rows = cursor.fetchall()
            for row in rows:
                messages.append({
                    "conversation_id": row[0],
                    "user_id": row[1],
                    "user_message": row[2],
                    "chatbot_message": row[3],
                    "timestamp": row[4].strftime("%Y-%m-%d %H:%M:%S")
                })
            return messages

    def get_message_count_by_user_id(
            self,
            user_id: int
    ) -> int:
        """
        Retrieve the count of messages sent by a given user_id across all conversations.

        Args:
            user_id: ID of the user.

        Returns:
            The count of messages sent by the given user_id across all conversations.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM ConversationHistory
                WHERE user_id = %s
                """,
                (user_id,)
            )
            return cursor.fetchone()[0]

    def get_message_count_by_user_and_conversation_id(
            self,
            user_id: int,
    ) -> int:
        """
        Retrieve the count of messages sent between two users across all conversations.

        Args:
            user_id: ID of the first user.
            companion_id: ID of the second user.

        Returns:
            The count of messages sent between the two users across all conversations.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM ConversationHistory
                WHERE user_id = %s              
                """,
                (user_id)
            )
            return cursor.fetchone()[0]

    def get_checkpoint_by_user_id(self, user_id: str):
        """
        Get Conversation Checkpoints for a specific user.

        Parameters:
            user_id (int): The unique identifier of the user.

        Returns:
            list: A list of dictionaries containing (history, memory_moving_summary_buffer) for the user.
        """
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT history, memory_moving_summary_buffer
                FROM ConversationCheckpoints
                WHERE user_id = %s
                """,
                (user_id,)
            )
            result = cursor.fetchone()

        if result:
            history_json, memory_moving_summary_buffer = result
            print(history_json)
            return history_json, memory_moving_summary_buffer
        else:
            return [], None  # If user_id not found, return an empty list and None for memory_moving_summary_buffer



