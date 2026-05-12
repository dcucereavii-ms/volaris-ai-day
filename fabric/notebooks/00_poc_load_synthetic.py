# Fabric notebook: 00_poc_load_synthetic
# POC shortcut: load synthetic data already in 'gold' shape (no enrichment).
# Use this for the POC instead of 01/02/03 to skip public-data dependencies.

from pyspark.sql import functions as F

SOURCE = "Files/synthetic/"   # uploaded via OneLake explorer or shortcut
TABLE = "gold_features"

df = (spark.read
      .option("recursiveFileLookup", "true")
      .parquet(SOURCE))

df = (df
      .withColumn("log_size_sqm", F.log1p(F.col("size_sqm")))
      .withColumn("age_years", F.lit(2026) - F.col("year_built"))
      # POC: no vision; impute neutral defaults so the model schema stays stable
      .withColumn("condition_score",  F.lit(0.6))
      .withColumn("roof_condition",   F.lit(0.6))
      .withColumn("curb_appeal",      F.lit(0.6))
      .withColumn("renovation_flag",  F.lit(0))
      .withColumn("has_vision_score", F.lit(0))
)

print(f"Rows: {df.count():,}")
df.printSchema()

(df.write
   .mode("overwrite")
   .format("delta")
   .option("overwriteSchema", "true")
   .partitionBy("sale_month")
   .saveAsTable(TABLE))

# Holdout = most recent 6 months
months = sorted(r["sale_month"] for r in df.select("sale_month").distinct().collect())
cutoff = months[-6]
holdout = df.filter(F.col("sale_month") >= cutoff)
training = df.filter(F.col("sale_month") < cutoff)

(training.write.mode("overwrite").format("delta")
   .option("overwriteSchema", "true")
   .partitionBy("sale_month")
   .saveAsTable("gold_features_training"))

(holdout.write.mode("overwrite").format("delta")
   .option("overwriteSchema", "true")
   .partitionBy("sale_month")
   .saveAsTable("gold_features_holdout"))

print(f"Training: {training.count():,} | Holdout: {holdout.count():,} (cutoff: {cutoff})")
