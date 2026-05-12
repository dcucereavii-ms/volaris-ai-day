# Fabric notebook: 02_silver_enrich
# Joins bronze with public datasets and writes silver_valuations_enriched.
# Assumes public datasets are already loaded as Delta tables in the lakehouse.

from pyspark.sql import functions as F

bronze = spark.table("bronze_valuations")

# Public datasets (loaded by separate ingestion pipelines)
osm  = spark.table("public_osm_h3_features")           # geo_h3_r8, dist_school, dist_transit, amenity_count_1km
cens = spark.table("public_census_postcode")           # postcode_prefix, median_income, unemployment_rate, pop_density
mac  = spark.table("public_macro_indicators")          # sale_month, mortgage_rate, cpi, regional_gdp_growth
haz  = spark.table("public_hazard_layers")             # geo_h3_r8, flood_zone, seismic_zone

silver = (bronze
    .join(F.broadcast(osm),  on="geo_h3_r8",      how="left")
    .join(F.broadcast(cens), on="postcode_prefix", how="left")
    .join(F.broadcast(mac),  on="sale_month",      how="left")
    .join(F.broadcast(haz),  on="geo_h3_r8",      how="left"))

print(f"Silver rows: {silver.count():,}")
silver.printSchema()

(silver.write
    .mode("overwrite")
    .format("delta")
    .option("overwriteSchema", "true")
    .partitionBy("sale_month")
    .saveAsTable("silver_valuations_enriched"))

print("Wrote silver_valuations_enriched")
