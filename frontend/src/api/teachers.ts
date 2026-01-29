import { apiFetch } from './client'

export type Teacher = {
  id: string
  code: string
  full_name: string
  weekly_off_day?: number | null
  max_per_day: number
  max_per_week: number
  max_continuous: number
  is_active: boolean
  created_at: string
}

export type TeacherCreate = Omit<Teacher, 'id' | 'created_at'>

export type TeacherPut = Pick<
  Teacher,
  | 'full_name'
  | 'weekly_off_day'
  | 'max_per_day'
  | 'max_per_week'
  | 'max_continuous'
  | 'is_active'
>

export async function listTeachers(): Promise<Teacher[]> {
  return apiFetch<Teacher[]>('/api/teachers/')
}

export async function createTeacher(payload: TeacherCreate): Promise<Teacher> {
  return apiFetch<Teacher>('/api/teachers/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deleteTeacher(id: string): Promise<{ ok: true }> {
  return apiFetch<{ ok: true }>(`/api/teachers/${id}`, { method: 'DELETE' })
}

export async function updateTeacher(id: string, payload: TeacherPut): Promise<Teacher> {
  return apiFetch<Teacher>(`/api/teachers/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}
