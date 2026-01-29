-- Drop unused teacher contact fields
-- Safe to run even if columns already removed.

ALTER TABLE IF EXISTS teachers
  DROP COLUMN IF EXISTS email,
  DROP COLUMN IF EXISTS phone;
