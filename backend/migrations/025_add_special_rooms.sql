-- Add special rooms: excluded from solver auto-assignment and usable only via Special Allotments.

ALTER TABLE rooms
    ADD COLUMN IF NOT EXISTS is_special boolean NOT NULL DEFAULT FALSE;

ALTER TABLE rooms
    ADD COLUMN IF NOT EXISTS special_note text;

-- Optional index to make filtering fast.
CREATE INDEX IF NOT EXISTS idx_rooms_is_special_true
    ON rooms (is_special)
    WHERE is_special IS TRUE;
