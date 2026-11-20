import { Link } from 'react-router-dom'

/** "Law" in navy (or white on dark backgrounds) + "Buddy" in teal. */
export default function Logo({ light = false, className = '' }: { light?: boolean; className?: string }) {
  return (
    <Link
      to="/"
      aria-label="LawBuddy home"
      className={`text-2xl font-extrabold tracking-tight ${light ? 'text-white' : 'text-navy'} ${className}`}
    >
      Law<span className="text-teal">Buddy</span>
    </Link>
  )
}
