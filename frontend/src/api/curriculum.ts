import { apiFetch } from './client'

export type TrackSubject = {
  id: string
  program_id: string
  track: 'CORE' | 'CYBER' | 'AI_DS' | 'AI_ML' | string
  subject_id: string
  is_elective: boolean
  sessions_override?: number | null
  created_at: string
}

export type TrackSubjectCreate = {
  program_code: string
  academic_year_number: number
  track: 'CORE' | 'CYBER' | 'AI_DS' | 'AI_ML' | string
  subject_code: string
  is_elective: boolean
  sessions_override?: number | null
}

export async function listTrackSubjects(params: {
  program_code: string
  academic_year_number: number
}): Promise<TrackSubject[]> {
  const qs = new URLSearchParams({
    program_code: params.program_code,
    academic_year_number: String(params.academic_year_number),
  })
  return apiFetch<TrackSubject[]>(`/api/curriculum/track-subjects?${qs.toString()}`)
}

export async function createTrackSubject(payload: TrackSubjectCreate): Promise<TrackSubject> {
  return apiFetch<TrackSubject>('/api/curriculum/track-subjects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deleteTrackSubject(id: string): Promise<{ ok: true }> {
  return apiFetch<{ ok: true }>(`/api/curriculum/track-subjects/${id}`, { method: 'DELETE' })
}
