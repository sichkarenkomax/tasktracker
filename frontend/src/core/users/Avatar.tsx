/**
 * A person's picture, or their first letter when they have none.
 *
 * Four call sites used to render that letter separately - the header, the member
 * list, the org chart and the staff page - and each had its own idea of the size
 * and its own copy of the fallback, so a change to either had to be made four
 * times and one of them was always forgotten. One component with three sizes is
 * the whole fix (stage 2.3).
 *
 * The image is loaded by the browser, not fetched and decoded here: it is the
 * same bytes either way, and `<img>` gets lazy loading, the broken-image state and
 * the cached copy for free.
 */
export function Avatar({
  src,
  name,
  size = 'md',
  className,
}: {
  src?: string | null
  name: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  const classes = ['avatar', `avatar--${size}`, className].filter(Boolean).join(' ')

  if (!src) {
    return (
      <span className={classes} aria-hidden="true">
        {initial(name)}
      </span>
    )
  }

  return (
    <img
      className={`${classes} avatar--image`}
      src={src}
      // The name is the accessible content: a photograph carries no meaning to a
      // screen reader, and the letter it replaces did say who this was.
      alt={name}
      loading="lazy"
      decoding="async"
      onError={(event) => {
        // A file can be deleted after this page rendered. Rather than leave a
        // broken-image glyph in the header, fall back to the letter.
        const element = event.currentTarget
        const letter = document.createElement('span')
        letter.className = classes
        letter.setAttribute('aria-hidden', 'true')
        letter.textContent = initial(name)
        element.replaceWith(letter)
      }}
    />
  )
}

export function initial(name: string): string {
  const trimmed = name.trim()
  return trimmed === '' ? '?' : trimmed.charAt(0).toUpperCase()
}