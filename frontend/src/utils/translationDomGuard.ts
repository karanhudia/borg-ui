// Browser page translators (Chrome, Safari) move or replace React's text nodes
// with their own <font> wrappers. React then removes or inserts against a text
// node that is no longer a direct child and the whole page crashes with
// NotFoundError (facebook/react#11538). Only those text nodes are handled here,
// where the translator left them; anything else gets the browser's own answer.
let installed = false

export const installTranslationDomGuard = (): void => {
  if (installed || typeof Node !== 'function') return
  installed = true

  const removeChild = Node.prototype.removeChild
  Node.prototype.removeChild = function <T extends Node>(this: Node, child: T): T {
    if (child instanceof Text && child.parentNode !== this) {
      // Replaced by the translator: nothing of it is left to remove.
      if (child.parentNode === null) return child
      // Moved into a wrapper under this parent: remove it there.
      if (this.contains(child.parentNode)) {
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
      // Replaced by the translator: append, as no position is left to keep.
      if (reference.parentNode === null) return insertBefore.call(this, node, null) as T
      // Inside a wrapper under this parent: insert before that wrapper.
      if (this.contains(reference)) {
        let anchor: Node = reference
        while (anchor.parentNode !== this) anchor = anchor.parentNode as Node
        return insertBefore.call(this, node, anchor) as T
      }
    }
    return insertBefore.call(this, node, reference) as T
  }
}
