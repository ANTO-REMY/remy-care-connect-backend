-- 031_alter_dietary_recommendation.sql
-- Expand nutrition schema to support structured Kenyan recommendations.

ALTER TABLE dietary_recommendation
  ADD COLUMN IF NOT EXISTS source_id VARCHAR(64),
  ADD COLUMN IF NOT EXISTS swahili_name VARCHAR,
  ADD COLUMN IF NOT EXISTS description TEXT,
  ADD COLUMN IF NOT EXISTS target_groups JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS trimester_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS meal_type VARCHAR(64),
  ADD COLUMN IF NOT EXISTS meal_time VARCHAR(32),
  ADD COLUMN IF NOT EXISTS key_nutrients JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS health_benefits JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS preparation_tips TEXT,
  ADD COLUMN IF NOT EXISTS cautions JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS nutrition_highlight VARCHAR(255),
  ADD COLUMN IF NOT EXISTS portion_guide TEXT,
  ADD COLUMN IF NOT EXISTS image_suggestion VARCHAR(255),
  ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS calories INTEGER,
  ADD COLUMN IF NOT EXISTS is_featured BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS source_name VARCHAR;

-- Ensure JSONB defaults are applied to existing rows
UPDATE dietary_recommendation
SET
  target_groups = COALESCE(target_groups, '[]'::jsonb),
  trimester_tags = COALESCE(trimester_tags, '[]'::jsonb),
  key_nutrients = COALESCE(key_nutrients, '[]'::jsonb),
  health_benefits = COALESCE(health_benefits, '[]'::jsonb),
  cautions = COALESCE(cautions, '[]'::jsonb),
  tags = COALESCE(tags, '[]'::jsonb)
WHERE COALESCE(target_groups::text, 'null') = 'null'
   OR COALESCE(trimester_tags::text, 'null') = 'null'
   OR COALESCE(key_nutrients::text, 'null') = 'null'
   OR COALESCE(health_benefits::text, 'null') = 'null'
   OR COALESCE(cautions::text, 'null') = 'null'
   OR COALESCE(tags::text, 'null') = 'null';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_dietary_recommendation_source_id'
  ) THEN
    ALTER TABLE dietary_recommendation
      ADD CONSTRAINT uq_dietary_recommendation_source_id UNIQUE (source_id);
  END IF;
END $$;
