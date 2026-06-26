// src/util.rs — small panic-free string helpers shared across screens.
// Canonical truncation primitive: every screen that shows a bounded preview of a
// daemon-supplied string routes through `head` so a multibyte boundary in crafted
// event data can never panic the render thread (DoS). Replaces ad-hoc `&s[..n]`
// byte slices that paniced on non-ASCII payloads.

/// Largest prefix of `s` containing at most `max_chars` characters.
/// Slices on a char boundary, so it never panics on multibyte input.
pub fn head(s: &str, max_chars: usize) -> &str {
    match s.char_indices().nth(max_chars) {
        Some((byte_idx, _)) => &s[..byte_idx],
        None => s,
    }
}

/// `head`, plus a `…` marker when the string was actually truncated.
pub fn head_ellipsis(s: &str, max_chars: usize) -> String {
    let h = head(s, max_chars);
    if h.len() < s.len() {
        format!("{h}…")
    } else {
        s.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn head_ascii_under_limit_is_identity() {
        assert_eq!(head("abc", 8), "abc");
    }

    #[test]
    fn head_ascii_truncates_at_char_count() {
        assert_eq!(head("abcdefgh", 3), "abc");
    }

    #[test]
    fn head_never_panics_on_multibyte_boundary() {
        // "héllo" — 'é' is 2 bytes; byte index 1 is NOT a char boundary.
        // A naive &s[..1] would panic here; head must not.
        let s = "héllo";
        assert_eq!(head(s, 1), "h");
        assert_eq!(head(s, 2), "hé");
        assert_eq!(head(s, 99), s);
    }

    #[test]
    fn head_handles_wide_emoji() {
        let s = "🦀🦀🦀"; // each crab is 4 bytes
        assert_eq!(head(s, 1), "🦀");
        assert_eq!(head(s, 2), "🦀🦀");
        assert_eq!(head(s, 100), s);
    }

    #[test]
    fn head_ellipsis_marks_truncation_only_when_cut() {
        assert_eq!(head_ellipsis("abcdefgh", 3), "abc…");
        assert_eq!(head_ellipsis("abc", 8), "abc");
        // multibyte: a 4-char string cut to 2 chars, no panic, marked.
        assert_eq!(head_ellipsis("héllo", 2), "hé…");
    }

    #[test]
    fn head_empty_string() {
        assert_eq!(head("", 5), "");
        assert_eq!(head_ellipsis("", 5), "");
    }
}
