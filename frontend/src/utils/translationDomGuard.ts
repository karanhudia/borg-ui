// Browser page translators (Chrome, Safari) move or replace React's text nodes
// with their own <font> wrappers. React then removes or inserts against a text
// node that is no longer a direct child and the whole page crashes with
// NotFoundError (facebook/react#11538). Only those text nodes are handled here,
// where the translator left them; anything else gets the browser's own answer.
let installed = false

// The direct child of `parent` that holds `node` through translator <font>
// wrappers only, or null when anything else stands between them.
const translationWrapper = (parent: Node, node: Node): Node | null => {
  let current = node.parentNode
  while (current && current !== parent) {
    if (current.nodeName !== 'FONT') return null
    if (current.parentNode === parent) return current
    current = current.parentNode
  }
  return null
}

export const installTranslationDomGuard = (): void => {
  if (installed || typeof Node !== 'function') return
  installed = true

  const removeChild = Node.prototype.removeChild
  Node.prototype.removeChild = function <T extends Node>(this: Node, child: T): T {
    if (child instanceof Text && child.parentNode !== this) {
      // Replaced by the translator: nothing of it is left to remove.
      if (child.parentNode === null) return child
      // Moved into a translator wrapper under this parent: remove it there.
      if (translationWrapper(this, child)) {
        removeChild.call(child.parentNode, child)
        return child
      }
    }
    return removeChild.call(this, child) as T
  }

  const insertBefore = Node.prototype.insertBefore
  Node.prototype.insertBefore = function <T extends Node>(
    this: Node,
    node: T,
    reference: Node | null
  ): T {
    if (reference instanceof Text && reference.parentNode !== this) {
      // Inside a translator wrapper under this parent: insert before it.
      const wrapper = translationWrapper(this, reference)
      if (wrapper) return insertBefore.call(this, node, wrapper) as T
      // Replaced by the translator: append a node React is placing here (new,
      // already a child, or a child the translator wrapped), as no position is
      // left to keep. A node from another container is not moved.
      if (
        reference.parentNode === null &&
        (node.parentNode === null ||
          node.parentNode === this ||
          translationWrapper(this, node) !== null)
      ) {
        return insertBefore.call(this, node, null) as T
      }
    }
    return insertBefore.call(this, node, reference) as T
  }
}
