export function clampAcademicYearNumber(n: number): number {
  const v = Number(n)
  if (!Number.isFinite(v)) return 1
  if (v < 1) return 1
  // Timetables in this project are currently supported for Years 1–3.
  if (v > 3) return 3
  return Math.trunc(v)
}

export function parseAcademicYearFromSectionCode(code: string): number | null {
  const text = String(code ?? '').trim()
  if (!text) return null

  // Supports common section formats used in this project:
  //   2A6, 3A12, Y2A6, y3-sec-1, etc.
  let m = /^\s*[Yy]\s*(\d+)/.exec(text)
  if (!m) m = /^\s*(\d+)/.exec(text)
  if (!m) return null

  const year = Number(m[1])
  if (!Number.isFinite(year)) return null
  return clampAcademicYearNumber(year)
}
