// Planted source for the hallucination fixture: a call to a symbol that is never defined.
// The function render_widget is called below but is declared nowhere; the referential_truth
// harness greps for its definition, does not find it, and exits nonzero. (This comment is
// worded to avoid the literal definition token so it cannot satisfy the grep by accident.)
pub fn build_view(x: u32) -> Widget {
    let w = render_widget(x); // unresolved: the definition does not exist anywhere
    w
}
