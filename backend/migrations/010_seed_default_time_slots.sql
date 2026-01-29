begin;

-- Seed default weekly time slots (Mon-Sat = day_of_week 0..5)
-- 6 one-hour slots/day.

with seed(day_of_week, slot_index, start_time, end_time) as (
  values
    (0,0,'09:00'::time,'10:00'::time),(0,1,'10:00'::time,'11:00'::time),(0,2,'11:00'::time,'12:00'::time),(0,3,'12:00'::time,'13:00'::time),(0,4,'14:00'::time,'15:00'::time),(0,5,'15:00'::time,'16:00'::time),
    (1,0,'09:00'::time,'10:00'::time),(1,1,'10:00'::time,'11:00'::time),(1,2,'11:00'::time,'12:00'::time),(1,3,'12:00'::time,'13:00'::time),(1,4,'14:00'::time,'15:00'::time),(1,5,'15:00'::time,'16:00'::time),
    (2,0,'09:00'::time,'10:00'::time),(2,1,'10:00'::time,'11:00'::time),(2,2,'11:00'::time,'12:00'::time),(2,3,'12:00'::time,'13:00'::time),(2,4,'14:00'::time,'15:00'::time),(2,5,'15:00'::time,'16:00'::time),
    (3,0,'09:00'::time,'10:00'::time),(3,1,'10:00'::time,'11:00'::time),(3,2,'11:00'::time,'12:00'::time),(3,3,'12:00'::time,'13:00'::time),(3,4,'14:00'::time,'15:00'::time),(3,5,'15:00'::time,'16:00'::time),
    (4,0,'09:00'::time,'10:00'::time),(4,1,'10:00'::time,'11:00'::time),(4,2,'11:00'::time,'12:00'::time),(4,3,'12:00'::time,'13:00'::time),(4,4,'14:00'::time,'15:00'::time),(4,5,'15:00'::time,'16:00'::time),
    (5,0,'09:00'::time,'10:00'::time),(5,1,'10:00'::time,'11:00'::time),(5,2,'11:00'::time,'12:00'::time),(5,3,'12:00'::time,'13:00'::time),(5,4,'14:00'::time,'15:00'::time),(5,5,'15:00'::time,'16:00'::time)
)
insert into time_slots(day_of_week, slot_index, start_time, end_time)
select day_of_week, slot_index, start_time, end_time
from seed
on conflict (day_of_week, slot_index)
do update set
  start_time = excluded.start_time,
  end_time = excluded.end_time;

commit;
