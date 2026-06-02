/// A fixture crate for G3 framework-reality gate testing.
pub fn hello() -> &'static str {
    "hello"
}

pub struct Widget {
    pub name: String,
}

impl Widget {
    pub fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
        }
    }

    pub fn greet(&self) -> String {
        format!("Hello, {}!", self.name)
    }
}

pub mod utils {
    pub fn helper() -> i32 {
        42
    }
}
