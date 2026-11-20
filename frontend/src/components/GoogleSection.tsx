import { useState } from 'react'

import GoogleButton from './GoogleButton'

/** Google button + "or continue with email" divider. Collapses to nothing when Google
 *  sign-in isn't configured, so the email form simply stands alone. */
export default function GoogleSection({ text, onCredential }: {
  text: 'signin_with' | 'signup_with'
  onCredential: (credential: string) => void
}) {
  const [available, setAvailable] = useState<boolean | null>(null)
  if (available === false) return null
  return (
    <div className={available ? '' : 'h-0 overflow-hidden'}>
      <GoogleButton text={text} onCredential={onCredential} onAvailable={setAvailable} />
      <div className="my-6 flex items-center gap-3 text-xs font-medium text-navy/50">
        <span className="h-px flex-1 bg-navy/10" />
        or continue with email
        <span className="h-px flex-1 bg-navy/10" />
      </div>
    </div>
  )
}
