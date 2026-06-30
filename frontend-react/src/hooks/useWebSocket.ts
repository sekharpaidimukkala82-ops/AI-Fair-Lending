import { useEffect, useRef, useCallback, useState } from 'react'

export interface WSEvent {
  event: string
  file_id?: string
  progress?: number
  step?: string
  status?: string
  error?: string
  [key: string]: unknown
}

interface UseWebSocketOptions {
  onMessage?: (event: WSEvent) => void
  enabled?: boolean
}

export function useTaskProgress(resourceId: string | null, options: UseWebSocketOptions = {}) {
  const { onMessage, enabled = true } = options
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState<WSEvent | null>(null)

  const connect = useCallback(() => {
    if (!resourceId || !enabled) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host || 'localhost:3000'
    const url = `${protocol}//${host}/ws/${resourceId}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
    }

    ws.onmessage = (e) => {
      try {
        const data: WSEvent = JSON.parse(e.data)
        setLastEvent(data)
        onMessage?.(data)
      } catch {}
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
    }

    ws.onerror = () => {
      setConnected(false)
    }
  }, [resourceId, enabled, onMessage])

  useEffect(() => {
    connect()

    // Ping every 25s to keep alive
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping')
      }
    }, 25_000)

    return () => {
      clearInterval(pingInterval)
      wsRef.current?.close()
    }
  }, [connect])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
  }, [])

  return { connected, lastEvent, disconnect }
}
