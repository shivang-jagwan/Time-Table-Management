export function clampAcademicYearNumber(n: number): number {
  const v = Number(n)
  if (!Number.isFinite(v)) return 1
  if (v < 1) return 1
  // Timetables in this project are currently supported for Years 1–3.
  if (v > 3) return 3
  return Math.trunc(v)
}
