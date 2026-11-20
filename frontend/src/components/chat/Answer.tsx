import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** Turn "[1]" / "[2][3]" citation markers into links we render as clickable chips. */
const withCiteLinks = (text: string) => text.replace(/\[(\d{1,2})\](?!\()/g, '[$1](#cite-$1)')

/** Assistant answer: Markdown (bold, lists, paragraphs) with clickable citation chips. */
export default function Answer({ text, onCite }: { text: string; onCite: (ref: number) => void }) {
  return (
    <div className="space-y-3 text-[15px] leading-relaxed text-navy [&_li]:my-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_strong]:font-bold [&_ul]:list-disc [&_ul]:pl-5">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const m = href?.match(/^#cite-(\d+)$/)
            if (m) {
              const ref = Number(m[1])
              return (
                <button
                  type="button"
                  onClick={() => onCite(ref)}
                  aria-label={`Source ${ref}`}
                  className="mx-0.5 inline-grid h-5 min-w-5 place-items-center rounded-md bg-teal/15 px-1 align-[1px] text-[11px] font-bold text-teal transition hover:bg-teal hover:text-white"
                >
                  {ref}
                </button>
              )
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" className="font-semibold text-teal underline">
                {children}
              </a>
            )
          },
          // The model writes short sections; keep headings modest inside a chat bubble.
          h1: ({ children }) => <p className="font-bold">{children}</p>,
          h2: ({ children }) => <p className="font-bold">{children}</p>,
          h3: ({ children }) => <p className="font-bold">{children}</p>,
        }}
      >
        {withCiteLinks(text)}
      </Markdown>
    </div>
  )
}
