//! An engine loaded on its first call and freed after a quiet spell.
//!
//! The fallback engine answers only when the primary hears nothing, a few
//! times a day. Keeping it resident cost ~0.6 GB on top of Parakeet (bench
//! 2026-10-16: 1.72 GB with both loaded, over the 1.5 GB budget), so it is
//! loaded when first needed and dropped once idle for [`FALLBACK_IDLE`].

use std::sync::{Arc, Condvar, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use crate::{Error, Transcriber};

/// How long the fallback engine stays loaded after its last call. A retry
/// right after a miss (the user dictates again) finds it warm; an idle Mac
/// gets the memory back.
pub const FALLBACK_IDLE: Duration = Duration::from_secs(30);

type Loader = dyn Fn() -> Result<Box<dyn Transcriber>, Error> + Send + Sync;

struct Slot {
    engine: Option<Box<dyn Transcriber>>,
    last_used: Instant,
    /// True while a thread is waiting to free the engine.
    has_reaper: bool,
}

struct Shared {
    slot: Mutex<Slot>,
    /// Wakes the reaper early when the engine is used or dropped.
    used: Condvar,
}

/// A [`Transcriber`] that loads its engine on the first call and frees it
/// after `idle` without a call. Clones share the same engine.
#[derive(Clone)]
pub struct Lazy {
    name: &'static str,
    idle: Duration,
    loader: Arc<Loader>,
    shared: Arc<Shared>,
}

impl Lazy {
    pub fn new(
        name: &'static str,
        idle: Duration,
        loader: impl Fn() -> Result<Box<dyn Transcriber>, Error> + Send + Sync + 'static,
    ) -> Self {
        Lazy {
            name,
            idle,
            loader: Arc::new(loader),
            shared: Arc::new(Shared {
                slot: Mutex::new(Slot {
                    engine: None,
                    last_used: Instant::now(),
                    has_reaper: false,
                }),
                used: Condvar::new(),
            }),
        }
    }

    /// Whether the engine is in memory right now.
    pub fn is_loaded(&self) -> bool {
        self.lock().engine.is_some()
    }

    fn lock(&self) -> MutexGuard<'_, Slot> {
        // A panic mid-inference leaves the engine in an unknown state: drop it
        // and load afresh rather than propagate the poison.
        self.shared.slot.lock().unwrap_or_else(|poisoned| {
            let mut slot = poisoned.into_inner();
            slot.engine = None;
            slot
        })
    }

    /// One short-lived thread per loaded period: it sleeps until the idle
    /// deadline, frees the engine if nothing used it since, and exits. No
    /// thread exists while the engine is not loaded.
    fn spawn_reaper(&self) {
        let shared = Arc::clone(&self.shared);
        let idle = self.idle;
        std::thread::spawn(move || {
            let mut slot = shared.slot.lock().unwrap_or_else(|p| p.into_inner());
            loop {
                if slot.engine.is_none() {
                    break;
                }
                let elapsed = slot.last_used.elapsed();
                if elapsed >= idle {
                    // Dropped outside the lock would race a new load; the
                    // drop is quick next to the 30 s it waited.
                    slot.engine = None;
                    break;
                }
                slot = shared
                    .used
                    .wait_timeout(slot, idle - elapsed)
                    .unwrap_or_else(|p| p.into_inner())
                    .0;
            }
            slot.has_reaper = false;
        });
    }
}

impl Transcriber for Lazy {
    fn name(&self) -> &'static str {
        self.name
    }

    fn transcribe(&mut self, samples: &[f32]) -> Result<String, Error> {
        let mut slot = self.lock();
        if slot.engine.is_none() {
            slot.engine = Some((self.loader)()?);
        }
        let result = slot
            .engine
            .as_mut()
            .expect("loaded just above")
            .transcribe(samples);
        slot.last_used = Instant::now();
        if !slot.has_reaper {
            slot.has_reaper = true;
            self.spawn_reaper();
        }
        self.shared.used.notify_all();
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    struct Echo;

    impl Transcriber for Echo {
        fn name(&self) -> &'static str {
            "echo"
        }
        fn transcribe(&mut self, samples: &[f32]) -> Result<String, Error> {
            Ok(samples.len().to_string())
        }
    }

    fn counted(idle: Duration) -> (Lazy, Arc<AtomicUsize>) {
        let loads = Arc::new(AtomicUsize::new(0));
        let counter = Arc::clone(&loads);
        let lazy = Lazy::new("echo", idle, move || {
            counter.fetch_add(1, Ordering::SeqCst);
            Ok(Box::new(Echo) as Box<dyn Transcriber>)
        });
        (lazy, loads)
    }

    fn wait_until(condition: impl Fn() -> bool) -> bool {
        let deadline = Instant::now() + Duration::from_secs(5);
        while Instant::now() < deadline {
            if condition() {
                return true;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        false
    }

    #[test]
    fn nothing_is_loaded_before_the_first_call() {
        let (lazy, loads) = counted(Duration::from_secs(30));
        assert!(!lazy.is_loaded());
        assert_eq!(loads.load(Ordering::SeqCst), 0);
    }

    #[test]
    fn calls_within_the_idle_spell_reuse_one_load() {
        let (mut lazy, loads) = counted(Duration::from_secs(30));
        assert_eq!(lazy.transcribe(&[0.0; 3]).unwrap(), "3");
        assert_eq!(lazy.transcribe(&[0.0; 5]).unwrap(), "5");
        assert!(lazy.is_loaded());
        assert_eq!(loads.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn the_engine_is_freed_after_the_idle_spell_and_reloaded_on_demand() {
        let (mut lazy, loads) = counted(Duration::from_millis(100));
        lazy.transcribe(&[0.0]).unwrap();
        assert!(wait_until(|| !lazy.is_loaded()), "never freed");
        lazy.transcribe(&[0.0]).unwrap();
        assert!(lazy.is_loaded());
        assert_eq!(loads.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn a_failed_load_is_reported_and_retried_next_call() {
        let attempts = Arc::new(AtomicUsize::new(0));
        let counter = Arc::clone(&attempts);
        let mut lazy = Lazy::new("flaky", Duration::from_secs(30), move || {
            if counter.fetch_add(1, Ordering::SeqCst) == 0 {
                Err(Error::ModelMissing("first try".to_string()))
            } else {
                Ok(Box::new(Echo) as Box<dyn Transcriber>)
            }
        });
        assert!(lazy.transcribe(&[0.0]).is_err());
        assert_eq!(lazy.transcribe(&[0.0]).unwrap(), "1");
    }
}
