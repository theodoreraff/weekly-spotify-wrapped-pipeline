from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, when, to_date
from pyspark.sql.types import StructType, StructField, StringType, IntegerType
from dotenv import load_dotenv
import os
import findspark


def get_schemas():
    artist_schema = StructType([
        StructField("artist_id", StringType(), True),
        StructField("name", StringType(), True),
        StructField("external_url", StringType(), True),
        StructField("follower_count", IntegerType(), True),
        StructField("image_url", StringType(), True),
        StructField("popularity", IntegerType(), True)
    ])

    return {
        "artist_topic": artist_schema
    }


def write_to_postgres(batch_df, batch_id):
    properties = {
        "user": os.getenv('PSQL_DB_USER'),
        "password": os.getenv('PSQL_DB_PASSWORD'),
        "driver": "org.postgresql.Driver",
        'url': os.getenv('PSQL_DB_LINK'),
        "dbtable": "dim_artist",
    }

    if not batch_df.isEmpty():
        batch_df.write.format('jdbc').options(**properties).mode('append').save()


def create_spark_session():
    return SparkSession.builder \
        .appName("artist-topic-spark-consumer") \
        .config("spark.jars", jdbc_jar) \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.3.2") \
        .getOrCreate()


def read_from_kafka(spark, kafka_bootstrap_servers, topics):
    return spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", kafka_bootstrap_servers) \
        .option("subscribe", topics) \
        .load()


def parse_json_data(df, schemas):
    artist_df = df.filter(col("topic") == "artist_topic") \
        .withColumn("parsed_data", from_json(col("json_value"), schemas["artist_topic"])) \
        .select(col("parsed_data.*"))

    return artist_df


def main():
    schemas = get_schemas()
    spark = create_spark_session()
    kafka_bootstrap_servers = "localhost:9092"
    topics = "artist_topic"  # Only consume artist_topic

    df = read_from_kafka(spark, kafka_bootstrap_servers, topics)
    df = df.selectExpr("CAST(value AS STRING) as json_value", "topic")
    df = parse_json_data(df, schemas)

    def process_batch(batch_df, batch_id):
        batch_df.printSchema()
        batch_df.show()
        write_to_postgres(batch_df, batch_id)

    query = df.writeStream \
        .foreachBatch(process_batch) \
        .outputMode("append") \
        .start()

    try:
        query.awaitTermination()
    except KeyboardInterrupt:
        print("Process interrupted by user.")
    finally:
        query.stop()
        print("Query stopped.")
        spark.stop()
        print("Spark session stopped.")


if __name__ == "__main__":
    spark_home = "your spark home directory"
    jdbc_jar = f"{spark_home}/jars/PostgreSQL-42.7.0.jar"
    findspark.init(spark_home)
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))
    main()