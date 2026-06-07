use axiom_cli::compute_cid;
use std::io::Write;
use std::process::{Command, Stdio};

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

#[test]
fn test_cli_accepts_exact_stdin_limit() {
    let exe = env!("CARGO_BIN_EXE_axiom-cli");
    let mut child = Command::new(exe)
        .arg("cid")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn axiom-cli");

    child
        .stdin
        .as_mut()
        .expect("stdin")
        .write_all(&vec![b'x'; 1_000_000])
        .expect("write exact limit");

    let output = child.wait_with_output().expect("wait for axiom-cli");
    assert!(
        output.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&output.stderr)
    );
}
