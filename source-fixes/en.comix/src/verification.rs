//! Verification cookies are opaque; an endpoint probe establishes current access.
use aidoku::alloc::{String, string::ToString};

#[derive(Default)]
pub struct VerificationState {
    candidate: Option<String>,
    checked_at: i64,
    verified: bool,
}

impl VerificationState {
    pub fn reset(&mut self) {
        *self = Self::default();
    }

    pub fn check<F: FnOnce() -> bool>(&mut self, cookie: Option<&str>, now: i64, probe: F) -> bool {
        let Some(cookie) = cookie.filter(|value| !value.trim().is_empty()
            && !value.chars().any(char::is_control)) else {
            self.reset();
            return false;
        };
        // Cookie callbacks can repeat while the verification sheet is open.
        // Cache only briefly; neither cookie contents nor a fixed lifetime imply access.
        if self.candidate.as_deref() == Some(cookie)
            && now >= self.checked_at && now - self.checked_at < 5 {
            return self.verified;
        }
        self.candidate = Some(cookie.to_string());
        self.checked_at = now;
        self.verified = probe();
        self.verified
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn opaque_cookie_is_accepted_only_when_the_endpoint_probe_succeeds() {
        let mut state = VerificationState::default();
        assert!(state.check(Some("opaque-current-token"), 100, || true));
        assert!(!state.check(Some("different-opaque-token"), 101, || false));
    }

    #[test]
    fn missing_or_empty_cookie_never_runs_a_probe() {
        for cookie in [None, Some(""), Some(" "), Some("bad\ncookie")] {
            assert!(!VerificationState::default().check(cookie, 100, || panic!("unexpected probe")));
        }
    }

    #[test]
    fn timestamp_format_is_not_treated_as_proof_of_verification() {
        assert!(!VerificationState::default().check(Some("99999999999.future"), 100, || false));
        assert!(VerificationState::default().check(Some("1.old-format"), 100, || true));
    }

    #[test]
    fn identical_callbacks_are_bounded_but_changed_cookies_recheck_immediately() {
        let mut state = VerificationState::default();
        assert!(!state.check(Some("first"), 100, || false));
        assert!(!state.check(Some("first"), 101, || panic!("repeated probe")));
        assert!(state.check(Some("second"), 101, || true));
        assert!(state.check(Some("second"), 102, || panic!("repeated probe")));
        assert!(!state.check(Some("second"), 106, || false));
    }

    #[test]
    fn reset_and_clock_rollback_do_not_reuse_an_old_result() {
        let mut state = VerificationState::default();
        assert!(state.check(Some("cookie"), 100, || true));
        assert!(!state.check(Some("cookie"), 99, || false));
        state.reset();
        assert!(state.check(Some("cookie"), 99, || true));
    }
}
