/**
 * Icono "?" con tooltip CSS puro (sin JS, funciona como Server Component).
 * Usalo junto a cualquier titulo/columna que necesite explicacion:
 *   <span>Hit rate <Info text={TERMS.hitRate} /></span>
 */
export function Info({ text }: { text: string }) {
  return (
    <span className="info-wrap" tabIndex={0}>
      <span className="info-dot" aria-hidden="true">?</span>
      <span className="info-tip" role="tooltip">{text}</span>
    </span>
  );
}

export function Label({ text, tip }: { text: string; tip: string }) {
  return (
    <span className="info-wrap" tabIndex={0}>
      {text} <span className="info-dot" aria-hidden="true">?</span>
      <span className="info-tip" role="tooltip">{tip}</span>
    </span>
  );
}
