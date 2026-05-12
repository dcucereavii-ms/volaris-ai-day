# Fabric notebook: 01_bronze_load
# Loads anonymized parquet files into bronze_valuations Delta table.
# Run in a Fabric workspace attached to the LH_PropertyValuation lakehouse.

from pyspark.sql import functions as F

SOURCE = "Files/anonymized/"      # OneLake shortcut to ADLS or direct upload
TABLE = "bronze_valuations"

df = (spark.read
      .option("recursiveFileLookup", "true")
      .parquet(SOURCE))

df = (df
      .withColumn("ingested_at", F.current_timestamp())
      .withColumn("source_file", F.input_file_name()))

print(f"Bronze rows to write: {df.count():,}")
df.printSchema()

(df.write
   .mode("overwrite")
   .format("delta")
   .option("overwriteSchema", "true")
   .saveAsTable(TABLE))

print(f"Wrote {TABLE}")
