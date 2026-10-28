export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options, 
    credentials: 'include', headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    const message = Array.isArray(detail)
      ? detail.map((entry: { msg: string }) => entry.msg).join(', ')
      : detail

    throw new ApiError(message || `Request failed (${response.status})`, response.status)
  }

  return response.status === 204 ? undefined as T : response.json()
}