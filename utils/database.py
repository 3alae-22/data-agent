import psycopg2
from psycopg2 import sql


class DataBaseUtil: 
 
    def __init__(self, db_config): 
        self.db_config = db_config 
 
        try: 
            self.connection = psycopg2.connect(**db_config) 
        except psycopg2.Error as e: 
            print(f"Error connecting to the database; {e}") 
            self.connection = None 
 
    def schema_details(self, schema_name): 
        cursor = None
        connection = self.connection
        
        try: 
            schema_info_context = "" 
 
            if connection is None:
                raise Exception("Database connection is not available.")

            cursor = connection.cursor() 
 
            schema_info_context = f"Database Schema: {schema_name}\n" 
 
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s;",
                (schema_name,)
            ) 
            table_list = cursor.fetchall() 
 
            for table in table_list: 
                table_name = table[0] 
                schema_info_context = f"{schema_info_context}\nTable: {table_name}\n" 
                
                cursor.execute(
                    "SELECT column_name, data_type "
                    "FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s;",
                    (schema_name, table_name)
                ) 
                columns_list = cursor.fetchall() 
 
                for column in columns_list: 
                    column_name, data_type = column 
                    schema_info_context = (
                        f"{schema_info_context} "
                        f"Column: {column_name}, Data Type: {data_type}\n"
                    ) 
 
                cursor.execute(
                    sql.SQL("SELECT * FROM {}.{} LIMIT 5;").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(table_name)
                    )
                ) 
                
                sample_data = cursor.fetchall() 
                schema_info_context = f"{schema_info_context} Sample Data:\n" 
                
                for row in sample_data: 
                    schema_info_context = f"{schema_info_context} {row}\n" 
 
        except Exception as e: 
            print(f"Error fetching schema details: {e}")     
            schema_info_context = f"Error fetching schema details: {e}" 
 
        finally: 
            if cursor: 
                cursor.close() 
            if connection: 
                connection.close() 
                 
        return schema_info_context

    def execute_query(self, query):
        cursor = None
        connection = self.connection
        try:
            cursor = connection.cursor()
            cursor.execute(query)
            result = cursor.fetchall()
            connection.commit()
            return str(result)
        except Exception as e:
            print(f"Error executing query: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

obj = DataBaseUtil ({
    "host": "localhost",
    "port": 5432,
    "user": "db_user",
    "password": "db_password",
    "dbname": "db"
})

result = obj.schema_details(schema_name="public")

with open("test_schema_details.txt", "w") as f:
    f.write(result)