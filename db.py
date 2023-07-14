
if __name__ == "__main__":
    import psycopg2

    # RDS endpoint (host)
    host = "vishalpsychoai.czsy9wvc3ecl.us-east-1.rds.amazonaws.com"

    # Database credentials
    dbname = "postgres"
    user = "postgres"
    password = "vishalpsychoai"

    # Connection string

    # Establish connection
    try:
        connection = psycopg2.connect(
            database=dbname,
            user=user,
            password=password,
            host=host,
            port='5432'
        )
        cursor = connection.cursor()
        print("Connected to the database!")

        # Execute queries or perform database operations here

        # Remember to close the connection
        cursor.close()
        connection.close()
        print("Connection closed.")
    except psycopg2.Error as e:
        print("Error connecting to the database:", e)
