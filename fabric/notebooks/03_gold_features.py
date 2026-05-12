# Fabric notebook: 03_gold_features
# Joins silver + vision features, derives ML-ready columns, writes gold_features.

from pyspark.sql import functions as F

silver = spark.table("silver_valuations_enriched")

# silver_property_vision is produced by the vision/ pipeline (Part 6).
# If not yet populated, this join still works and yields nulls (handled below).
try:
    vision = spark.table("silver_property_vision")
    has_vision = True
except Exception:
    vision = None
    has_vision = False
    print("WARNING: silver_property_vision not found; proceeding without vision features.")

gold = silver

if has_vision:
    gold = gold.join(vision, on="property_hash", how="left")

gold = (gold
    .withColumn("log_size_sqm", F.log1p(F.col("size_sqm")))
    .withColumn("age_years",    F.lit(2026) - F.col("year_built"))
    .withColumn("has_vision_score",
                F.when(F.col("condition_score").isNotNull(), 1).otherwise(0)
                if has_vision else F.lit(0))
)

# Impute missing vision features with neutral defaults
if has_vision:
    gold = gold.fillna({
        "condition_score":   0.6,
        "roof_condition":    0.6,
        "curb_appeal":       0.6,
        "renovation_flag":   0,
    })

print(f"Gold rows: {gold.count():,}")
gold.printSchema()

(gold.write
    .mode("overwrite")
    .format("delta")
    .option("overwriteSchema", "true")
    .partitionBy("sale_month")
    .saveAsTable("gold_features"))

# Optimize for ML reads
spark.sql("OPTIMIZE gold_features ZORDER BY (geo_h3_r8, property_type)")
print("Wrote gold_features")
