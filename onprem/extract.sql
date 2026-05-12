-- extract.sql
-- Stratified 10% sample of last 5 years of valuations.
-- Adjust column/table names to your source schema.
-- Run on-prem; export result to staging/raw_extract.parquet.

WITH stratified AS (
  SELECT
    v.property_id,
    v.owner_name,         -- dropped during anonymize
    v.owner_id,           -- dropped during anonymize
    v.account_number,     -- dropped during anonymize
    v.street_address,     -- dropped during anonymize
    v.postcode,
    v.latitude,
    v.longitude,
    v.property_type,
    v.size_sqm,
    v.rooms,
    v.bathrooms,
    v.year_built,
    v.sale_date,
    v.sale_price,
    -- Derived size band for k-anon grouping
    CASE
      WHEN v.size_sqm <  40 THEN '<40'
      WHEN v.size_sqm < 100 THEN '40-100'
      WHEN v.size_sqm < 200 THEN '100-200'
      ELSE '200+'
    END AS size_band,
    v.region_code,
    ROW_NUMBER() OVER (
      PARTITION BY v.region_code, v.property_type, YEAR(v.sale_date)
      ORDER BY NEWID()
    ) AS rn,
    COUNT(*) OVER (
      PARTITION BY v.region_code, v.property_type, YEAR(v.sale_date)
    ) AS bucket_size
  FROM valuations v
  WHERE v.sale_date >= DATEADD(YEAR, -5, GETDATE())
    AND v.sale_price IS NOT NULL
    AND v.size_sqm  IS NOT NULL
)
SELECT *
FROM stratified
WHERE rn <= CEILING(bucket_size * 0.10);
