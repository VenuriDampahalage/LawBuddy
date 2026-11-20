import { useEffect, useRef, useState } from 'react'

import { getAuthConfig } from '../lib/api'

/** Minimal typings for Google Identity Services (https://accounts.google.com/gsi/client). */
type GsiButtonOptions = {
  type: 'standard'
  theme: 'outline' | 'filled_blue' | 'filled_black'
  size: 'large' | 'medium' | 'small'
  shape: 'pill' | 'rectangular'
  text: 'signin_with' | 'signup_with' | 'continue_with'
  width: number
  logo_alignment: 'left' | 'center'
  locale?: string
}
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: {
            client_id: string
            callback: (r: { credential?: string }) => void
            ux_mode?: 'popup' | 'redirect'
            auto_select?: boolean
            cancel_on_tap_outside?: boolean
          }) => void
          renderButton: (el: HTMLElement, opts: GsiButtonOptions) => void
        }
      }
    }
  }
}

// hl=en: English button text regardless of the browser language (the site is English-only)
const GSI_SRC = 'https://accounts.google.com/gsi/client?hl=en'
let gsiPromise: Promise<void> | null = null
let clientIdPromise: Promise<string | null> | null = null

function loadGsi(): Promise<void> {
  gsiPromise ??= new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve()
    const s = document.createElement('script')
    s.src = GSI_SRC
    s.async = true
    s.onload = () => resolve()
    s.onerror = () => {
      gsiPromise = null
      reject(new Error('Could not load Google sign-in'))
    }
    document.head.appendChild(s)
  })
  return gsiPromise
}

function googleClientId(): Promise<string | null> {
  clientIdPromise ??= getAuthConfig()
    .then((c) => c.google_client_id)
    .catch(() => {
      clientIdPromise = null
      return null
    })
  return clientIdPromise
}

/**
 * Google's official "Sign in with Google" button. Renders nothing (and `onAvailable(false)`)
 * when Google sign-in isn't configured on the server or Google's script can't load.
 */
export default function GoogleButton({ text, onCredential, onAvailable }: {
  text: 'signin_with' | 'signup_with'
  onCredential: (credential: string) => void
  onAvailable?: (available: boolean) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [ready, setReady] = useState(false)
  // Keep the latest callback without re-rendering Google's button on every parent render.
  const callbackRef = useRef(onCredential)
  useEffect(() => {
    callbackRef.current = onCredential
  }, [onCredential])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const clientId = await googleClientId()
      if (!clientId) return onAvailable?.(false)
      try {
        await loadGsi()
      } catch {
        return onAvailable?.(false)
      }
      if (cancelled || !ref.current || !window.google) return
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (r) => r.credential && callbackRef.current(r.credential),
        ux_mode: 'popup',
        auto_select: false,
        cancel_on_tap_outside: true,
      })
      window.google.accounts.id.renderButton(ref.current, {
        type: 'standard',
        theme: 'outline',
        size: 'large',
        shape: 'pill',
        text,
        width: Math.min(400, Math.max(200, Math.floor(ref.current.clientWidth))),
        logo_alignment: 'center',
        // The site is English-only; otherwise Google follows the browser language.
        locale: 'en',
      })
      setReady(true)
      onAvailable?.(true)
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text])

  return <div ref={ref} className={`flex h-11 w-full justify-center ${ready ? '' : 'invisible'}`} />
}
