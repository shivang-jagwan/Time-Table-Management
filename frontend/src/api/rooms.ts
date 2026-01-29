import { apiFetch } from './client'

export type Room = {
  id: string
  code: string
  name: string
  room_type: 'CLASSROOM' | 'LT' | 'LAB' | string
  capacity: number
  is_active: boolean
  created_at: string
}

export type RoomCreate = {
  code: string
  name: string
  room_type: 'CLASSROOM' | 'LT' | 'LAB' | string
  capacity: number
  is_active: boolean
}

export type RoomPut = RoomCreate

export async function listRooms(): Promise<Room[]> {
  return apiFetch<Room[]>('/api/rooms/')
}

export async function createRoom(payload: RoomCreate): Promise<Room> {
  return apiFetch<Room>('/api/rooms/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deleteRoom(id: string): Promise<{ ok: true }> {
  return apiFetch<{ ok: true }>(`/api/rooms/${id}`, { method: 'DELETE' })
}

export async function putRoom(id: string, payload: RoomPut): Promise<Room> {
  return apiFetch<Room>(`/api/rooms/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}
