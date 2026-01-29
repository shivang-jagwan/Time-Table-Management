import { apiFetch } from './client'

export type Program = {
  code: string
  name: string
}

export type ProgramCreate = {
  code: string
  name: string
}

export async function listPrograms(): Promise<Program[]> {
  return apiFetch<Program[]>('/api/programs')
}

export async function createProgram(payload: ProgramCreate): Promise<Program> {
  return apiFetch<Program>('/api/programs', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deleteProgram(code: string): Promise<{ ok: true }> {
  return apiFetch<{ ok: true }>(`/api/programs/${encodeURIComponent(code)}`,
    { method: 'DELETE' },
  )
}
