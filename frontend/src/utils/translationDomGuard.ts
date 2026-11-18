// Browser page translators (Chrome, Safari) move text nodes into their own
// <font> wrappers. React then removes or inserts against a node that is no longer
// a direct child and the whole page crashes with NotFoundError
// (facebook/react#11538). Act on where the node is now instead, so translation
// keeps working and React's view of the page stays in step.
let installed = false

export const installTranslationDomGuard = (): void => {
  if (installed || typeof Node !== 'function') return
  installed = true

  const removeChild = Node.prototype.removeChild
  Node.prototype.removeChild = function <T extends Node>(this: Node, child: T): T {
    if (child.parentNode === this) return removeChild.call(this, child) as T
    // Moved into a wrapper: remove it there, so no stale text stays visible.
    // Already dropped by the translator: nothing left to remove.
    if (child.parentNode) removeChild.call(child.parentNode, child)
    return child
  }

  const insertBefore = Node.prototype.insertBefore
  Node.prototype.insertBefore = function <T extends Node>(
    this: Node,
    node: T,
    reference: Node | null
  ): T {
    if (reference && reference.parentNode !== this) {
      // Insert before the direct child that wraps the reference; append when
      // the reference left this parent altogether.
      let anchor: Node | null = reference
      while (anchor && anchor.parentNode !== this) anchor = anchor.parentNode
      return insertBefore.call(this, node, anchor) as T
    }
    return insertBefore.call(this, node, reference) as T
  }
}
