import { LoaderCircle } from 'lucide-react'

export default function Spinner({ label, size = 28 }: { label: string; size?: number }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-navy/60">
      <LoaderCircle className="animate-spin text-teal" size={size} aria-hidden />
      <span className="sr-only">{label}</span>
    </span>
  )
}
