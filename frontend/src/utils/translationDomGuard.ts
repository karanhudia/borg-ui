// Browser page translators (Chrome, Safari) move text nodes into their own
// <font> wrappers. React then removes or inserts against a node that is no longer
// a child and the whole page crashes with NotFoundError. This is the workaround
// from facebook/react#11538: tolerate a node someone else moved, keep translation.
let installed = false

export const installTranslationDomGuard = (): void => {
  if (installed || typeof Node !== 'function') return
  installed = true

  const removeChild = Node.prototype.removeChild
  Node.prototype.removeChild = function <T extends Node>(this: Node, child: T): T {
    if (child.parentNode !== this) return child
    return removeChild.call(this, child) as T
  }

  const insertBefore = Node.prototype.insertBefore
  Node.prototype.insertBefore = function <T extends Node>(
    this: Node,
    node: T,
    reference: Node | null
  ): T {
    if (reference && reference.parentNode !== this) return this.appendChild(node)
    return insertBefore.call(this, node, reference) as T
  }
}
