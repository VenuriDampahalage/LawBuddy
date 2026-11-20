import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <section className="mx-auto max-w-xl px-6 py-32 text-center">
      <p className="text-sm font-bold text-teal">404</p>
      <h1 className="mt-2 text-3xl font-extrabold">Page not found</h1>
      <Link to="/" className="mt-8 inline-block font-semibold text-teal hover:underline">
        Back to home
      </Link>
    </section>
  )
}
