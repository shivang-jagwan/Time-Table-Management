BEGIN;

-- Seed the 4 supported academic years (1–4)
INSERT INTO academic_years (year_number, is_active)
VALUES
  (1, true),
  (2, true),
  (3, true),
  (4, true)
ON CONFLICT (year_number) DO NOTHING;

COMMIT;
