/**
 * useStreamBuffers – frontend token buffering for natural streaming feel
 * ======================================================================
 * SSE tokens arrive as fast as the LLM generates them.  This module queues
 * them and drains into React state at a smooth, character-level pace so text
 * appears to be "typed" rather than dumped all at once.
 *
 * Architecture:
 *   - One TokenBuffer per logical stream (main content, main reasoning,
 *     subagent:<name>:content, subagent:<name>:reasoning).
 *   - A single requestAnimationFrame loop drives ALL active buffers and
 *     batches a single setMessages() call per frame (~60/sec max).
 *   - push() never triggers re-renders — it only enqueues.
 *   - The RAF drain loop is the ONLY thing that calls setMessages().
 */

// ── TokenBuffer (plain JS, no React) ──────────────────────────────────────────

const REASONING_BASE_SPEED = 0  // 0ms = natural LLM speed (instant SSE render for reasoning)
const REASONING_MIN_SPEED  = 0
const CONTENT_BASE_SPEED   = 33  // ms per character (~30 chars/sec -> steady response typing)
const CONTENT_MIN_SPEED    = 28  // ms per character (~35 chars/sec max under acceleration -> stays very slow and steady)
const FLUSH_SPEED          = 2   // ms per character during flush (rapid drain)
const QUEUE_ACCEL_THRESHOLD = 200  // queue length (in characters) before acceleration starts

class TokenBuffer {
  constructor(baseSpeed = CONTENT_BASE_SPEED, minSpeed = CONTENT_MIN_SPEED) {
    this.queue = []        // pending character strings
    this.revealed = ''     // text revealed so far
    this.flushing = false  // true after flush() — drain fast
    this._lastDrain = 0   // timestamp of last drain
    this.baseSpeed = baseSpeed
    this.minSpeed  = minSpeed
  }

  /** Enqueue a token chunk as individual characters (does NOT trigger renders). */
  push(text) {
    if (!text) return
    for (let i = 0; i < text.length; i++) {
      this.queue.push(text[i])
    }
  }

  /** Mark buffer for rapid drain (called on stream end). */
  flush() {
    this.flushing = true
  }

  /** Returns true if there are still tokens to drain. */
  get pending() {
    return this.queue.length > 0
  }

  /**
   * Drain tokens that are "due" based on elapsed time.
   * Returns the NEW text added this frame (empty string if nothing drained).
   */
  drain(now) {
    if (this.queue.length === 0) return ''

    const speed = this.flushing
      ? FLUSH_SPEED
      : this._adaptiveSpeed()

    if (speed <= 0) {
      let added = ''
      while (this.queue.length > 0) {
        const tok = this.queue.shift()
        this.revealed += tok
        added += tok
      }
      this._lastDrain = now
      return added
    }

    if (!this._lastDrain) this._lastDrain = now

    const elapsed = now - this._lastDrain
    // How many tokens we can drain this frame
    const count = Math.max(1, Math.floor(elapsed / speed))

    let added = ''
    for (let i = 0; i < count && this.queue.length > 0; i++) {
      const tok = this.queue.shift()
      this.revealed += tok
      added += tok
    }

    if (added) this._lastDrain = now
    return added
  }

  /** Speed adapts: large queue → faster drain to keep up. */
  _adaptiveSpeed() {
    const depth = this.queue.length
    if (depth <= QUEUE_ACCEL_THRESHOLD) return this.baseSpeed
    // Linearly interpolate between baseSpeed and minSpeed
    const t = Math.min(1, (depth - QUEUE_ACCEL_THRESHOLD) / 300)
    return this.baseSpeed - t * (this.baseSpeed - this.minSpeed)
  }

  reset() {
    this.queue = []
    this.revealed = ''
    this.flushing = false
    this._lastDrain = 0
  }
}


// ── useStreamBuffers React hook ───────────────────────────────────────────────

import { useRef, useCallback, useEffect } from 'react'

/**
 * Hook that manages a set of named TokenBuffers and a single RAF drain loop.
 *
 * Usage:
 *   const buf = useStreamBuffers(setMessages, asstIdRef)
 *   buf.push('main:content', tokenText)
 *   buf.push('sub:inventory_agent:reasoning', tokenText)
 *   buf.flushAll()      // on stream done
 *   buf.reset()         // on new message
 *
 * The drain loop applies buffered text to setMessages() once per frame.
 */
export default function useStreamBuffers(setMessages) {
  const buffersRef    = useRef(new Map())   // key → TokenBuffer
  const rafRef        = useRef(null)        // animation frame id
  const activeRef     = useRef(false)       // is the loop running?
  const asstIdRef     = useRef(null)        // current assistant message id
  const isFlushingRef = useRef(false)       // true once flushAll() is called

  /** Get or create a buffer for the given key. */
  const getBuffer = useCallback((key) => {
    if (!buffersRef.current.has(key)) {
      const isReasoning = key.endsWith(':reasoning')
      const baseSpeed = isReasoning ? REASONING_BASE_SPEED : CONTENT_BASE_SPEED
      const minSpeed  = isReasoning ? REASONING_MIN_SPEED  : CONTENT_MIN_SPEED
      buffersRef.current.set(key, new TokenBuffer(baseSpeed, minSpeed))
    }
    return buffersRef.current.get(key)
  }, [])

  /**
   * Enforce strict sequential typing:
   * 1. main:reasoning types first.
   * 2. sub:<src>:reasoning types next.
   * 3. sub:<src>:content types after subagent reasoning is done.
   * 4. main:content (the final response) types ONLY after ALL reasoning and subagent streams finish.
   */
  const canDrain = useCallback(function canDrain(key, buffers) {
    if (key === 'main:reasoning') {
      return true
    }

    const mainReasoning = buffers.get('main:reasoning')
    if (mainReasoning && mainReasoning.pending) {
      return false
    }

    if (key.startsWith('sub:')) {
      if (key.endsWith(':reasoning')) {
        return true
      }
      if (key.endsWith(':content')) {
        const src = key.slice(4, -8)
        const subReasoning = buffers.get(`sub:${src}:reasoning`)
        if (subReasoning && subReasoning.pending) {
          return false
        }
        return true
      }
    }

    if (key === 'main:content') {
      for (const [otherKey, otherBuf] of buffers.entries()) {
        if (otherKey !== 'main:content' && otherBuf.pending) {
          return false
        }
      }
      return true
    }

    return true
  }, [])

  const drainFrame = useCallback(function drainFrame(timestamp) {
    if (!activeRef.current) return

    const id = asstIdRef.current
    if (!id) {
      rafRef.current = requestAnimationFrame(drainFrame)
      return
    }

    // Collect all drained text this frame, grouped by update type
    let mainContentDelta = ''
    let mainReasoningDelta = ''
    const subContentDeltas = {}    // src → delta
    const subReasoningDeltas = {}  // src → delta

    let anyPending = false

    for (const [key, buf] of buffersRef.current.entries()) {
      if (!buf.pending) continue

      // Enforce strict sequential order — wait if prerequisite stream is still typing out
      if (!canDrain(key, buffersRef.current)) {
        anyPending = true
        continue
      }

      const delta = buf.drain(timestamp)
      if (buf.pending) anyPending = true

      if (!delta) continue

      if (key === 'main:content') {
        mainContentDelta += delta
      } else if (key === 'main:reasoning') {
        mainReasoningDelta += delta
      } else if (key.startsWith('sub:') && key.endsWith(':content')) {
        const src = key.slice(4, -8) // strip 'sub:' and ':content'
        subContentDeltas[src] = (subContentDeltas[src] || '') + delta
      } else if (key.startsWith('sub:') && key.endsWith(':reasoning')) {
        const src = key.slice(4, -10) // strip 'sub:' and ':reasoning'
        subReasoningDeltas[src] = (subReasoningDeltas[src] || '') + delta
      }
    }

    // Apply a single batched setMessages if anything drained
    const hasDelta = mainContentDelta || mainReasoningDelta ||
      Object.keys(subContentDeltas).length > 0 ||
      Object.keys(subReasoningDeltas).length > 0

    if (hasDelta) {
      setMessages(prev => prev.map(m => {
        if (m.id !== id) return m

        let next = m

        if (mainContentDelta) {
          next = { ...next, content: next.content + mainContentDelta }
        }
        if (mainReasoningDelta) {
          next = { ...next, reasoning: (next.reasoning || '') + mainReasoningDelta }
        }

        const subSources = new Set([
          ...Object.keys(subContentDeltas),
          ...Object.keys(subReasoningDeltas),
        ])

        if (subSources.size > 0) {
          const newSubStreams = { ...next.subStreams }
          for (const src of subSources) {
            const existing = newSubStreams[src] || {}
            newSubStreams[src] = {
              ...existing,
              ...(subContentDeltas[src]
                ? { content: (existing.content || '') + subContentDeltas[src] }
                : {}),
              ...(subReasoningDeltas[src]
                ? { reasoning: (existing.reasoning || '') + subReasoningDeltas[src] }
                : {}),
            }
          }
          next = { ...next, subStreams: newSubStreams }
        }

        return next
      }))
    }

    // Continue loop if anything is still pending
    if (anyPending) {
      rafRef.current = requestAnimationFrame(drainFrame)
    } else {
      // Stream is completely drained
      if (isFlushingRef.current && id) {
        setMessages(prev => prev.map(m =>
          m.id === id ? { ...m, streaming: false } : m
        ))
        isFlushingRef.current = false
      }
      activeRef.current = false
      rafRef.current = null
    }
  }, [canDrain, setMessages])

  const startLoop = useCallback(() => {
    if (activeRef.current) return
    activeRef.current = true
    rafRef.current = requestAnimationFrame(drainFrame)
  }, [drainFrame])

  const stopLoop = useCallback(() => {
    activeRef.current = false
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [])

  /** Push a token into a named buffer. */
  const push = useCallback((key, text) => {
    getBuffer(key).push(text)
    startLoop()
  }, [getBuffer, startLoop])

  /** Flush all buffers (call on 'done' event). */
  const flushAll = useCallback(() => {
    isFlushingRef.current = true
    for (const buf of buffersRef.current.values()) {
      buf.flush()
    }
    // Ensure loop is running to drain remaining text
    startLoop()
  }, [startLoop])

  /** Reset all buffers (call when starting a new message). */
  const reset = useCallback(() => {
    stopLoop()
    isFlushingRef.current = false
    for (const buf of buffersRef.current.values()) {
      buf.reset()
    }
    buffersRef.current.clear()
  }, [stopLoop])

  /** Set the current assistant message ID that the drain loop targets. */
  const setAsstId = useCallback((id) => {
    asstIdRef.current = id
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => stopLoop()
  }, [stopLoop])

  return { push, flushAll, reset, setAsstId }
}