use axiom_cli::compute_cid;

#[test]
fn test_deterministic_and_distinct() {
    assert_eq!(compute_cid(b"hello"), compute_cid(b"hello"));
    assert_ne!(compute_cid(b"hello"), compute_cid(b"world"));
}

#[test]
fn test_full_width_256_bit() {
    let cid = compute_cid(b"x");
    let parts: Vec<&str> = cid.split(':').collect();
    assert_eq!(parts[0], "b2b256");
    assert_eq!(parts[1].len(), 64);
}
