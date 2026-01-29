import { apiFetch } from './client'

export type TimetableGridEntry = {
  day: number
  slot_index: number
  start_time: string
  end_time: string
  section_code: string
  subject_code: string
  teacher_name: string
  room_code: string
  year_number: number

  elective_block_id?: string | null
  elective_block_name?: string | null
}

function withRunId(path: string, runId?: string) {
  if (!runId) return path
  const qs = new URLSearchParams({ run_id: runId })
  return `${path}?${qs.toString()}`
}

export async function getSectionTimetable(sectionId: string, runId?: string): Promise<TimetableGridEntry[]> {
  return apiFetch<TimetableGridEntry[]>(withRunId(`/api/timetable/section/${sectionId}`, runId))
}

export async function getRoomTimetable(roomId: string, runId?: string): Promise<TimetableGridEntry[]> {
  return apiFetch<TimetableGridEntry[]>(withRunId(`/api/timetable/room/${roomId}`, runId))
}

export async function getFacultyTimetable(teacherId: string, runId?: string): Promise<TimetableGridEntry[]> {
  return apiFetch<TimetableGridEntry[]>(withRunId(`/api/timetable/faculty/${teacherId}`, runId))
}
